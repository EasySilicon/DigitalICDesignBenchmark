// Exact two-net repair of the measured seed47 final DRC. No router search.
#include <array>
#include <sstream>
#include <stdexcept>
#include <string>
#include "dbWire.h"
#include "dbWireOpcode.h"
#include "odb/db.h"
#include "odb/dbShape.h"
#include "odb/dbWireCodec.h"
#include "ord/OpenRoad.hh"

struct Tcl_Interp;
struct Tcl_Obj;
using ClientData = void*;
using Tcl_ObjCmdProc = int(ClientData, Tcl_Interp*, int, Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*, const char*, Tcl_ObjCmdProc*, ClientData, void (*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*, int);
void Tcl_SetObjResult(Tcl_Interp*, Tcl_Obj*);
const char* Tcl_GetString(Tcl_Obj*);
}

namespace {
struct Selected { odb::dbNet* net; odb::_dbWire* raw; unsigned index; odb::dbTechVia* via; };
Selected select(odb::dbBlock* block, odb::dbTech* tech, const char* name,
                const char* via_name, int x, int y) {
  auto* net=block->findNet(name); auto* via=tech->findVia(via_name);
  if (!net || !net->getWire() || !via) throw std::runtime_error("missing net/via");
  auto* raw=reinterpret_cast<odb::_dbWire*>(net->getWire());
  unsigned count=0, index=0;
  for (unsigned i=1;i<net->getWire()->length();++i) {
    if ((raw->opcodes_[i]&WOP_OPCODE_MASK)!=odb::kTechVia || raw->data_[i]!=static_cast<int>(via->getId())) continue;
    odb::WirePoint point;
    odb::getPrevPoint(tech,block,raw->opcodes_,raw->data_,i-1,false,point);
    if (point.x==x && point.y==y) {++count;index=i;}
  }
  if (count!=1) throw std::runtime_error("target via is absent/ambiguous");
  return {net,raw,index,via};
}
odb::dbVia* reshape(odb::dbBlock* block,odb::dbTech* tech,const char* name,const char* base,
                    std::array<int,4> expected) {
  auto* original=tech->findVia(base);
  if (!original || block->findVia(name)) throw std::runtime_error("unexpected stack via state");
  unsigned count=0;
  for (auto* box:original->getBoxes()) if (box->getTechLayer()->getName()=="M4") {
    if (std::array<int,4>{box->xMin(),box->yMin(),box->xMax(),box->yMax()}!=expected)
      throw std::runtime_error("unexpected M4 via footprint");
    ++count;
  }
  if (count!=1) throw std::runtime_error("unexpected M4 box count");
  auto* via=odb::dbVia::create(block,name);
  for (auto* box:original->getBoxes()) {
    bool lower=box->getTechLayer()->getName()=="M4";
    odb::dbBox::create(via,box->getTechLayer(),lower?-12:box->xMin(),lower?-23:box->yMin(),
                      lower?12:box->xMax(),lower?23:box->yMax());
  }
  return via;
}
void segment(odb::dbWireEncoder& encoder,odb::dbTech* tech,const char* layer,int x0,int y0,int x1,int y1) {
  encoder.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);
  encoder.addPoint(x0,y0); encoder.addPoint(x1,y1);
}
void via(odb::dbWireEncoder& encoder,odb::dbTech* tech,const char* layer,const char* name,int x,int y) {
  encoder.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);
  encoder.addPoint(x,y); encoder.addTechVia(tech->findVia(name));
}
int patch(ClientData,Tcl_Interp* interp,int objc,Tcl_Obj* const objv[]) {
  try {
    if (objc!=2) throw std::runtime_error("usage: t10_seed47 inspect|apply|apply_local");
    std::string mode=Tcl_GetString(objv[1]);
    if (mode!="inspect" && mode!="apply" && mode!="apply_local") throw std::runtime_error("invalid mode");
    auto* db=ord::OpenRoad::openRoad()->getDb();
    auto* block=db->getChip()->getBlock(); auto* tech=db->getTech();
    auto m2=select(block,tech,"net16515","VIA23",365013,271971);
    auto m4=select(block,tech,"quad_sum\\[3\\]\\[215\\]","VIA45",364956,270828);
    std::ostringstream report;
    for (auto p:{m2,m4}) {
      report<<p.net->getName()<<" length="<<p.net->getWire()->length()<<" via_index="<<p.index;
      for (unsigned i=p.index-4;i<p.net->getWire()->length() && i<=p.index+2;++i)
        report<<" ["<<i<<":"<<static_cast<unsigned>(p.raw->opcodes_[i])<<","<<p.raw->data_[i]<<"]";
      report<<"\n";
    }
    if (mode!="inspect") {
      // Guards are checked before any edit. The M4 via must be an isolated
      // path: moving this point must not move the long existing M5 column.
      if (m2.net->getWire()->length()!=155 || m4.net->getWire()->length()!=511 || m4.index<3 ||
          (m4.raw->opcodes_[m4.index-3]&WOP_OPCODE_MASK)!=odb::kPath ||
          (m4.raw->opcodes_[m4.index-2]&WOP_OPCODE_MASK)!=odb::kX || m4.raw->data_[m4.index-2]!=364956 ||
          (m4.raw->opcodes_[m4.index-1]&WOP_OPCODE_MASK)!=odb::kY || m4.raw->data_[m4.index-1]!=270828 ||
          m4.index+2!=m4.net->getWire()->length() ||
          (m4.raw->opcodes_[m4.index+1]&WOP_OPCODE_MASK)!=odb::kColor || m4.raw->data_[m4.index+1]!=0)
        throw std::runtime_error("unexpected M4 isolated-via wire encoding");
      unsigned endpoint=0,count=0;
      if (mode=="apply_local") {
        odb::dbWireShapeItr iterator; odb::dbShape shape;
        iterator.begin(m4.net->getWire());
        while (iterator.next(shape)) {
          auto box=shape.getBox();
          if (!shape.isVia() && shape.getTechLayer()->getName()=="M4" &&
              std::array<int,4>{box.xMin(),box.yMin(),box.xMax(),box.yMax()}==std::array<int,4>{363993,270816,364968,270840}) {
            endpoint=iterator.getShapeId(); ++count;
          }
        }
        if (count!=1 || (m4.raw->opcodes_[endpoint]&WOP_OPCODE_MASK)!=odb::kX || m4.raw->data_[endpoint]!=364956)
          throw std::runtime_error("unexpected M4 incoming segment endpoint");
      }
      const char* name="T10_S47_VIA23_M2_R9";
      if (block->findVia(name)) throw std::runtime_error("patch already present");
      unsigned boxes=0;
      for (auto* box:m2.via->getBoxes()) {
        if (box->getTechLayer()->getName()=="M2") {
          if (std::array<int,4>{box->xMin(),box->yMin(),box->xMax(),box->yMax()}!=std::array<int,4>{-14,-9,14,9})
            throw std::runtime_error("unexpected original M2 enclosure");
          ++boxes;
        }
        if (box->getTechLayer()->getName()=="V2" &&
            (box->xMin() < -14 || box->yMin() < -9 || box->xMax()>9 || box->yMax()>9))
          throw std::runtime_error("M2 crop would uncover cut");
      }
      if (boxes!=1) throw std::runtime_error("unexpected M2 box count");
      auto* replacement=odb::dbVia::create(block,name);
      for (auto* box:m2.via->getBoxes()) {
        bool lower=box->getTechLayer()->getName()=="M2";
        odb::dbBox::create(replacement,box->getTechLayer(),box->xMin(),box->yMin(),lower?9:box->xMax(),box->yMax());
      }
      m2.raw->opcodes_[m2.index]=(m2.raw->opcodes_[m2.index]&~WOP_OPCODE_MASK)|odb::kVia;
      m2.raw->data_[m2.index]=replacement->getId();
      odb::dbWireEncoder encoder;
      if (mode=="apply") {
        m4.raw->data_[m4.index-2]=364908;
        encoder.append(m4.net->getWire());
        segment(encoder,tech,"M5",364908,270828,364956,270828);
        encoder.end();
        report<<"APPLIED prototype nets=2 M4_via_move=-48nm M5_jog=48nm (native RECTONLY rejected)\n";
      } else {
        // Same rule-conserving topology as the verified v15 case-3 repair:
        // straight, unmodified M5 column; M2/M3 feed a rectangular M4 stack.
        auto* via45=reshape(block,tech,"T10_S47_VIA45_M4_STACK","VIA45",{-23,-12,23,12});
        auto* via34=reshape(block,tech,"T10_S47_VIA34_M4_STACK","VIA34",{-20,-12,20,12});
        m4.raw->data_[endpoint]=364848;
        m4.raw->opcodes_[m4.index]=(m4.raw->opcodes_[m4.index]&~WOP_OPCODE_MASK)|odb::kVia;
        m4.raw->data_[m4.index]=via45->getId();
        encoder.append(m4.net->getWire());
        segment(encoder,tech,"M3",364848,270756,364848,270828);
        segment(encoder,tech,"M2",364848,270756,364956,270756);
        segment(encoder,tech,"M3",364956,270756,364956,270828);
        via(encoder,tech,"M3","VIA34",364848,270828);
        via(encoder,tech,"M2","VIA23",364848,270756);
        via(encoder,tech,"M2","VIA23",364956,270756);
        encoder.newPath(tech->findLayer("M3"),odb::dbWireType::ROUTED);
        encoder.addPoint(364956,270828); encoder.addVia(via34);
        encoder.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);
        encoder.addPoint(364956,270828); encoder.addRect(-12,-42,12,42);
        encoder.end();
        report<<"APPLIED local nets=2 M5_unchanged M4_rectangle=24x84nm M2_M3_feed\n";
      }
    }
    Tcl_SetObjResult(interp,Tcl_NewStringObj(report.str().c_str(),-1)); return 0;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(error.what(),-1)); return 1;
  }
}
}
extern "C" int T10seed47_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_seed47",patch,nullptr,nullptr);return 0;
}
