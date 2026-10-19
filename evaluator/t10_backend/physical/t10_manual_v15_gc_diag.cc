// Diagnostic only: inspect the router's imported geometry and shift its
// checker window grid. Does not alter/write the OpenDB physical database.
#include <sstream>
#include <map>
#include <omp.h>
#include <type_traits>
#include "fmt/format.h"
// The diagnostic build host has fmt 9, which lacks the enum adapter used by
// this OpenROAD source revision. This affects diagnostic text formatting only.
namespace fmt {
template <typename T>
struct formatter<T, char, std::enable_if_t<std::is_enum_v<T>>> : formatter<int> {
  template <typename Context>
  auto format(T value, Context& ctx) const {
    return formatter<int>::format(static_cast<int>(value), ctx);
  }
};
}
#include "drt/TritonRoute.h"
#include "frDesign.h"
#include "gc/FlexGC.h"
#include "ord/OpenRoad.hh"
struct Tcl_Interp; struct Tcl_Obj; using ClientData=void*;
using Tcl_ObjCmdProc=int(ClientData,Tcl_Interp*,int,Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*,const char*,Tcl_ObjCmdProc*,ClientData,void(*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*,int); void Tcl_SetObjResult(Tcl_Interp*,Tcl_Obj*);
int Tcl_GetIntFromObj(Tcl_Interp*,Tcl_Obj*,int*);
const char* Tcl_GetString(Tcl_Obj*);
}
namespace {
int diagnose(ClientData,Tcl_Interp* interp,int objc,Tcl_Obj* const objv[]) {
  if(objc!=2) return 1;
  int shift=0; if(Tcl_GetIntFromObj(interp,objv[1],&shift)!=0) return 1;
  auto* router=ord::OpenRoad::openRoad()->getTritonRoute();
  auto* block=router->getDesign()->getTopBlock();
  if(!block) return 1;
  std::ostringstream out;
  auto* cfg=router->getRouterConfiguration();
  out<<"DRCSAFEDIST="<<cfg->DRCSAFEDIST<<" MTSAFEDIST="<<cfg->MTSAFEDIST;
  auto* net=block->findNet("net13604");
  if(net) for(const auto& shape:net->getShapes()) {
    auto rect=shape->getBBox();
    if(shape->getLayerNum()==4 && rect.intersects(odb::Rect(111000,147400,111500,147800)))
      out<<" M2="<<rect.xMin()<<","<<rect.yMin()<<","<<rect.xMax()<<","<<rect.yMax();
  }
  auto patterns=block->getGCellPatterns();
  for(auto& p:patterns) { p.setStartCoord(p.getStartCoord()+shift); p.setCount(p.getCount()+7); }
  block->setGCellPatterns(patterns);
  out<<" checker_grid_shift="<<shift;
  Tcl_SetObjResult(interp,Tcl_NewStringObj(out.str().c_str(),-1));
  return 0;
}

// Reproduce TritonRoute::getDRCMarkers with one extra scope check: a marker
// must intersect the DRC box of the worker that actually checked it. Otherwise
// polygons clipped at that worker's 4000 nm context edge leak into the report.
// All die positions remain covered by the original overlapping 500 nm boxes.
int full_check(ClientData,Tcl_Interp* interp,int objc,Tcl_Obj* const objv[]) {
  if(objc!=2) return 1;
  auto* app=ord::OpenRoad::openRoad();
  auto* router=app->getTritonRoute();
  auto* design=router->getDesign();
  auto* block=design->getTopBlock();
  if(!block) return 1;
  auto* cfg=router->getRouterConfiguration();
  const auto& patterns=block->getGCellPatterns();
  if(patterns.size()!=2 || patterns[0].getStartCoord()!=0 || patterns[1].getStartCoord()!=0
     || patterns[0].getSpacing()!=570 || patterns[1].getSpacing()!=570) return 1;
  const auto required=block->getBBox();
  struct Worker {std::unique_ptr<drt::FlexGCWorker> gc; odb::Rect drc;};
  std::vector<Worker> batch;
  std::list<std::unique_ptr<drt::frMarker>> raw,kept;
  std::map<drt::MarkerId,bool> raw_ids,kept_ids;
  unsigned workers=0;
  omp_set_num_threads(8);
  auto process=[&]() {
    #pragma omp parallel for schedule(dynamic)
    for(int k=0;k<static_cast<int>(batch.size());++k) {
      batch[k].gc->init(design); batch[k].gc->main();
    }
    for(const auto& worker:batch) for(const auto& marker:worker.gc->getMarkers()) {
      const auto box=marker->getBBox();
      if(!box.intersects(required)) continue;
      drt::MarkerId id{box,marker->getLayerNum(),marker->getConstraint(),marker->getSrcs()};
      if(raw_ids.emplace(id,true).second) raw.push_back(std::make_unique<drt::frMarker>(*marker));
      if(box.intersects(worker.drc) && kept_ids.emplace(id,true).second)
        kept.push_back(std::make_unique<drt::frMarker>(*marker));
    }
    batch.clear();
  };
  for(int i=0;i<patterns[0].getCount();i+=7) for(int j=0;j<patterns[1].getCount();j+=7) {
    auto first=block->getGCellBox(odb::Point(i,j));
    auto last=block->getGCellBox(odb::Point(std::min<int>(patterns[0].getCount()-1,i+6),
                                          std::min<int>(patterns[1].getCount(),j+6)));
    odb::Rect route(first.xMin(),first.yMin(),last.xMax(),last.yMax()),drc,ext;
    route.bloat(cfg->DRCSAFEDIST,drc); route.bloat(cfg->MTSAFEDIST,ext);
    auto gc=std::make_unique<drt::FlexGCWorker>(design->getTech(),app->getLogger(),cfg);
    gc->setDrcBox(drc); gc->setExtBox(ext);
    batch.push_back({std::move(gc),drc}); ++workers;
    if(batch.size()==128) process();
  }
  process();
  const std::string output=Tcl_GetString(objv[1]);
  router->reportDRC(output+".raw",raw,"RAW_CONTEXT_DIAGNOSTIC",required);
  router->reportDRC(output,kept,"FULL_CHECKED_SCOPE",required);
  std::ostringstream out;
  out<<"workers="<<workers<<" raw_unique="<<raw.size()<<" checked_scope="<<kept.size()
     <<" context_only="<<raw.size()-kept.size()<<" DRCSAFEDIST="<<cfg->DRCSAFEDIST
     <<" MTSAFEDIST="<<cfg->MTSAFEDIST;
  Tcl_SetObjResult(interp,Tcl_NewStringObj(out.str().c_str(),-1));
  return 0;
}
}
extern "C" int T10manualv15gcdiag_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_manual_v15_gc_diag",diagnose,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_manual_v15_gc_full",full_check,nullptr,nullptr); return 0;
}
