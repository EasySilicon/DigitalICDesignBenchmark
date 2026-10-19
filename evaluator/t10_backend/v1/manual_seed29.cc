// Bounded, deterministic seed29 ECO. Native DRC is the acceptance authority.
#include <array>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "dbWire.h"
#include "dbWireOpcode.h"
#include "odb/db.h"
#include "odb/dbShape.h"
#include "odb/dbWireCodec.h"
#include "ord/OpenRoad.hh"

struct Tcl_Interp;
struct Tcl_Obj;
using ClientData = void*;
using Tcl_ObjCmdProc = int(ClientData,Tcl_Interp*,int,Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*,const char*,Tcl_ObjCmdProc*,ClientData,void (*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*,int);
void Tcl_SetObjResult(Tcl_Interp*,Tcl_Obj*);
const char* Tcl_GetString(Tcl_Obj*);
}
namespace {
int command(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const argv[]) {
  try {
    if(argc!=2) throw std::runtime_error("usage: t10_seed29 inspect|apply_bridge|apply_bridge_and_crop");
    std::string mode=Tcl_GetString(argv[1]);
    if(mode!="inspect" && mode!="apply_bridge" && mode!="apply_bridge_and_crop" && mode!="apply_local" && mode!="apply_clearance_bridge") throw std::runtime_error("bad mode");
    auto* db=ord::OpenRoad::openRoad()->getDb();
    auto* block=db->getChip()->getBlock(); auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[471\\]");
    if(!net || !net->getWire()) throw std::runtime_error("net missing");
    auto* wire=net->getWire(); auto* raw=reinterpret_cast<odb::_dbWire*>(wire);
    if(wire->length()!=372) throw std::runtime_error("unexpected original wire length");
    std::vector<unsigned> starts;
    for(unsigned i=0;i<wire->length();++i) {
      auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kPath) starts.push_back(i);
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)
        throw std::runtime_error("cross-path reference requires separate audit");
    }
    starts.push_back(wire->length());
    std::map<unsigned,std::vector<odb::dbShape>> shapes;
    odb::dbWireShapeItr it; odb::dbShape shape; it.begin(wire);
    while(it.next(shape)) {
      unsigned id=it.getShapeId(),start=0;
      for(auto p:starts) { if(p>id) break;start=p; }
      shapes[start].push_back(shape);
    }
    std::ostringstream report; std::vector<std::pair<unsigned,unsigned>> remove;
    for(unsigned k=0;k+1<starts.size();++k) {
      auto begin=starts[k],end=starts[k+1]; bool inside=true,any=false;
      report<<"PATH "<<begin<<":"<<end;
      for(auto s:shapes[begin]) {
        auto b=s.getBox(); any=true;
        bool local=b.xMin()>=364700 && b.yMin()>=284350 && b.xMax()<=365450 && b.yMax()<=285140;
        inside&=local;
        report<<" shape="<<b.xMin()<<","<<b.yMin()<<","<<b.xMax()<<","<<b.yMax();
      }
      for(unsigned i=begin;i<end;++i) {
        auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
        if(op==odb::kIterm || op==odb::kBterm) inside=false;
      }
      if(any && inside) remove.emplace_back(begin,end);
      report<<(any&&inside?" REMOVE":" KEEP")<<"\n";
    }
    if(mode!="inspect") {
      const std::vector<std::pair<unsigned,unsigned>> expected={
        {131,136},{146,151},{151,156},{156,161},{161,166},{166,171},{171,176},
        {311,316},{316,321},{321,326},{326,331},{331,336},{336,341},{341,346},
        {346,351},{358,365},{365,372}};
      if(remove!=expected) throw std::runtime_error("unexpected local paths; inspect first");
      for(auto [begin,end]:remove) for(unsigned i=begin;i<end;++i) {
        raw->opcodes_[i]=odb::kNop;raw->data_[i]=0;
      }
      odb::dbWireEncoder encoder; encoder.append(wire);
      auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
        encoder.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);
        encoder.addPoint(x0,y0);encoder.addPoint(x1,y1);
      };
      auto via=[&](const char* layer,const char* name,int x,int y) {
        auto* v=tech->findVia(name);if(!v) throw std::runtime_error("via missing");
        encoder.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);
        encoder.addPoint(x,y);encoder.addTechVia(v);
      };
      if(mode=="apply_clearance_bridge") {
        // Reviewed fixed coordinates from the expanded supply-aware study.
        // Unlike the rejected prototype, no M2 segment crosses a PG rail.
        segment("M3",361377,284895,361377,286524);
        segment("M4",361377,286524,361932,286524);
        segment("M5",361932,286524,361932,286608);
        segment("M6",361932,286608,362384,286608);
        segment("M7",362384,286608,362384,291216);
        segment("M6",362384,291216,365676,291216);
        segment("M5",365676,285084,365676,291216);
        via("M2","VIA23",361377,284895);
        via("M3","VIA34",361377,286524);
        via("M4","VIA45",361932,286524);
        via("M5","VIA56",361932,286608);
        via("M6","VIA67",362384,286608);
        via("M6","VIA67",362384,291216);
        via("M5","VIA56",365676,291216);
        via("M4","VIA45",365676,285084);
      } else {
        segment("M3",361377,284895,361377,286731);
        segment("M2",361377,286731,365733,286731);
        segment("M3",365733,285084,365733,286731);
        via("M2","VIA23",361377,284895);
        via("M2","VIA23",361377,286731);
        via("M2","VIA23",365733,286731);
        via("M3","VIA34",365733,285084);
      }
      encoder.end();
      report<<"APPLIED one-net bounded bridge; all old external paths preserved\n";
      if(mode=="apply_bridge_and_crop" || mode=="apply_local" || mode=="apply_clearance_bridge") {
        auto* cropnet=block->findNet("quad_sum\\[3\\]\\[469\\]");
        auto* base=tech->findVia("VIA23");
        if(!cropnet || !cropnet->getWire() || !base || block->findVia("T10_S29_VIA23_M2_R9"))
          throw std::runtime_error("unexpected crop input");
        auto* cr=reinterpret_cast<odb::_dbWire*>(cropnet->getWire());unsigned index=0,count=0;
        for(unsigned i=1;i<cropnet->getWire()->length();++i) {
          if((cr->opcodes_[i]&WOP_OPCODE_MASK)!=odb::kTechVia || cr->data_[i]!=static_cast<int>(base->getId())) continue;
          odb::WirePoint p;odb::getPrevPoint(tech,block,cr->opcodes_,cr->data_,i-1,false,p);
          if(p.x==365013 && p.y==284463) {index=i;++count;}
        }
        if(count!=1) throw std::runtime_error("crop via absent/ambiguous");
        count=0;
        for(auto* b:base->getBoxes()) {
          if(b->getTechLayer()->getName()=="M2") {
            if(std::array<int,4>{b->xMin(),b->yMin(),b->xMax(),b->yMax()}!=std::array<int,4>{-14,-9,14,9})
              throw std::runtime_error("unexpected M2 plate");
            ++count;
          }
          if(b->getTechLayer()->getName()=="V2" && (b->xMin() < -14 || b->yMin() < -9 || b->xMax()>9 || b->yMax()>9))
            throw std::runtime_error("cropped plate would uncover cut");
        }
        if(count!=1) throw std::runtime_error("unexpected M2 box count");
        auto* v=odb::dbVia::create(block,"T10_S29_VIA23_M2_R9");
        for(auto* b:base->getBoxes())
          odb::dbBox::create(v,b->getTechLayer(),b->xMin(),b->yMin(),
                            b->getTechLayer()->getName()=="M2"?9:b->xMax(),b->yMax());
        cr->opcodes_[index]=(cr->opcodes_[index]&~WOP_OPCODE_MASK)|odb::kVia;cr->data_[index]=v->getId();
        report<<"APPLIED net469 M2 via plate right edge -5nm, cut unchanged\n";
      }
      if(mode=="apply_local") {
        auto removePatch=[&](const char* name,unsigned length,unsigned index,
                             std::array<int,7> expected) {
          auto* n=block->findNet(name);
          if(!n || !n->getWire() || n->getWire()->length()!=length)
            throw std::runtime_error("patch wire changed");
          auto* r=reinterpret_cast<odb::_dbWire*>(n->getWire());
          const std::array<unsigned,7> codes={odb::kPath,odb::kX,odb::kY,odb::kRect,
                                             odb::kOperand,odb::kOperand,odb::kOperand};
          for(unsigned i=0;i<7;++i)
            if((r->opcodes_[index+i]&WOP_OPCODE_MASK)!=codes[i] || r->data_[index+i]!=expected[i])
              throw std::runtime_error("unexpected isolated RECT encoding");
          for(unsigned i=0;i<length;++i) {
            auto op=r->opcodes_[i]&WOP_OPCODE_MASK;
            if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)
              throw std::runtime_error("patch net has cross-path references");
          }
          for(unsigned i=index;i<index+7;++i) {r->opcodes_[i]=odb::kNop;r->data_[i]=0;}
          report<<"REMOVED redundant isolated RECT "<<name<<" path="<<index<<"\n";
        };
        // Remaining ordinary wire + via plates form rectangles above min area.
        // No via cut or ordinary routed segment is changed by these removals.
        removePatch("quad_sum\\[3\\]\\[559\\]",636,629,{18,365229,284988,-59,-12,-20,12});
        removePatch("quad_sum\\[3\\]\\[301\\]",492,478,{18,365004,284748,23,-12,37,12});
        removePatch("quad_sum\\[3\\]\\[301\\]",492,485,{20,365004,284748,-12,-38,12,-23});
      }
    }
    Tcl_SetObjResult(interp,Tcl_NewStringObj(report.str().c_str(),-1));return 0;
  } catch(const std::exception& error) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(error.what(),-1));return 1;
  }
}
}
extern "C" int T10seed29_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_seed29",command,nullptr,nullptr);return 0;
}
