// Native, grid-aligned local DRC for ECO diagnostics only, NOT full qualification.
#include <sstream>
#include <map>
#include <omp.h>
#include <type_traits>
#include "fmt/format.h"
namespace fmt {
template <typename T>
struct formatter<T,char,std::enable_if_t<std::is_enum_v<T>>>:formatter<int> {
  template <typename Context> auto format(T value,Context& ctx) const {
    return formatter<int>::format(static_cast<int>(value),ctx);
  }
};
}
#include "drt/TritonRoute.h"
#include "frDesign.h"
#include "gc/FlexGC.h"
#include "ord/OpenRoad.hh"
struct Tcl_Interp;struct Tcl_Obj;using ClientData=void*;
using Tcl_ObjCmdProc=int(ClientData,Tcl_Interp*,int,Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*,const char*,Tcl_ObjCmdProc*,ClientData,void(*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*,int);void Tcl_SetObjResult(Tcl_Interp*,Tcl_Obj*);
int Tcl_GetIntFromObj(Tcl_Interp*,Tcl_Obj*,int*);
const char* Tcl_GetString(Tcl_Obj*);
}
namespace {
int check(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const argv[]) {
  if(argc!=6)return 1;
  int b[4];for(int i=0;i<4;++i)if(Tcl_GetIntFromObj(interp,argv[i+2],&b[i]))return 1;
  if(b[0]>=b[2] || b[1]>=b[3])return 1;
  const odb::Rect required(b[0],b[1],b[2],b[3]);
  auto* app=ord::OpenRoad::openRoad();auto* router=app->getTritonRoute();
  auto* design=router->getDesign();auto* block=design->getTopBlock();if(!block)return 1;
  auto* cfg=router->getRouterConfiguration();const auto& p=block->getGCellPatterns();
  if(p.size()!=2 || p[0].getStartCoord()!=0 || p[1].getStartCoord()!=0 ||
     p[0].getSpacing()!=570 || p[1].getSpacing()!=570)return 1;
  struct Worker {std::unique_ptr<drt::FlexGCWorker> gc;odb::Rect drc;};
  std::vector<Worker> batch;
  for(int i=0;i<p[0].getCount();i+=7)for(int j=0;j<p[1].getCount();j+=7) {
    auto first=block->getGCellBox(odb::Point(i,j));
    auto last=block->getGCellBox(odb::Point(std::min<int>(p[0].getCount()-1,i+6),
                                                        std::min<int>(p[1].getCount(),j+6)));
    odb::Rect route(first.xMin(),first.yMin(),last.xMax(),last.yMax()),drc,ext;
    route.bloat(cfg->DRCSAFEDIST,drc);if(!drc.intersects(required))continue;
    route.bloat(cfg->MTSAFEDIST,ext);
    auto gc=std::make_unique<drt::FlexGCWorker>(design->getTech(),app->getLogger(),cfg);
    gc->setDrcBox(drc);gc->setExtBox(ext);batch.push_back({std::move(gc),drc});
  }
  omp_set_num_threads(8);
  #pragma omp parallel for schedule(dynamic)
  for(int i=0;i<static_cast<int>(batch.size());++i) {batch[i].gc->init(design);batch[i].gc->main();}
  std::list<std::unique_ptr<drt::frMarker>> kept;std::map<drt::MarkerId,bool> ids;
  for(const auto& worker:batch)for(const auto& marker:worker.gc->getMarkers()) {
    auto box=marker->getBBox();
    drt::MarkerId id{box,marker->getLayerNum(),marker->getConstraint(),marker->getSrcs()};
    if(box.intersects(required) && box.intersects(worker.drc) && ids.emplace(id,true).second)
      kept.push_back(std::make_unique<drt::frMarker>(*marker));
  }
  router->reportDRC(Tcl_GetString(argv[1]),kept,"LOCAL_DIAGNOSTIC_NOT_FULL_QUALIFICATION",required);
  std::ostringstream out;out<<"LOCAL_ONLY workers="<<batch.size()<<" violations="<<kept.size();
  Tcl_SetObjResult(interp,Tcl_NewStringObj(out.str().c_str(),-1));return 0;
}
}
extern "C" int T10window_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_gc_window",check,nullptr,nullptr);return 0;
}
