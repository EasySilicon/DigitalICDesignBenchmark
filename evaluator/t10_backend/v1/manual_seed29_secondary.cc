// Fixed seed29 local edits; independent candidate file, native checks mandatory.
#include <array>
#include <algorithm>
#include <map>
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
struct Tcl_Interp;struct Tcl_Obj;using ClientData=void*;
using Tcl_ObjCmdProc=int(ClientData,Tcl_Interp*,int,Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*,const char*,Tcl_ObjCmdProc*,ClientData,void(*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*,int);void Tcl_SetObjResult(Tcl_Interp*,Tcl_Obj*);
}
namespace {
int apply(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_secondary");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[569\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=757)throw std::runtime_error("unexpected net569 wire");
    auto* wire=net->getWire();auto* raw=reinterpret_cast<odb::_dbWire*>(wire);
    std::vector<unsigned> starts;std::map<unsigned,std::vector<odb::dbShape>> shapes;
    for(unsigned i=0;i<757;++i) {
      auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kPath)starts.push_back(i);
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    starts.push_back(757);odb::dbWireShapeItr it;odb::dbShape shape;it.begin(wire);
    while(it.next(shape)) {
      unsigned start=0;for(auto p:starts) {if(p>it.getShapeId())break;start=p;}
      shapes[start].push_back(shape);
    }
    std::vector<unsigned> selected;
    for(unsigned k=0;k+1<starts.size();++k) {
      unsigned begin=starts[k],end=starts[k+1];bool inside=!shapes[begin].empty();
      for(auto s:shapes[begin]) {auto b=s.getBox();inside&=b.xMin()>=364700 && b.yMin()>=282000 && b.xMax()<=365700 && b.yMax()<=286200;}
      for(unsigned i=begin;i<end;++i) {
        auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
        if(op==odb::kIterm || op==odb::kBterm)inside=false;
      }
      if(inside) {if(end!=begin+5)throw std::runtime_error("non-isolated target path");selected.push_back(begin);}
    }
    const std::vector<unsigned> expected={281,286,291,296,346,356,361,616,656,661,666,671,676,681,731};
    if(selected!=expected)throw std::runtime_error("unexpected bounded removal");
    for(auto begin:selected)for(unsigned i=begin;i<begin+5;++i) {raw->opcodes_[i]=odb::kNop;raw->data_[i]=0;}
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);
    };
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));
    };
    segment("M3",363213,282105,363213,282444);
    segment("M4",363213,282444,363228,282444);
    // One M6 track lower than the first study: retain the full 48nm M5 EOL keepout.
    segment("M5",363228,282444,363228,282576);
    segment("M6",363228,282576,363280,282576);
    segment("M7",363280,282576,363280,286928);
    segment("M6",363280,286928,363708,286928);
    segment("M5",363708,286928,363708,291564);
    segment("M4",363708,291564,365805,291564);
    segment("M3",365805,286011,365805,291564);
    via("M2","VIA23",363213,282105);via("M3","VIA34",363213,282444);
    via("M4","VIA45",363228,282444);via("M5","VIA56",363228,282576);
    via("M6","VIA67",363280,282576);via("M6","VIA67",363280,286928);
    via("M5","VIA56",363708,286928);via("M4","VIA45",363708,291564);
    via("M3","VIA34",365805,291564);via("M2","VIA23",365805,286011);
    // Straight 24x84nm M4 rectangle: preserve RECTONLY and minimum area.
    enc.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);
    enc.addPoint(363227,282444);enc.addRect(-42,-12,42,12);enc.end();

    auto* edge=block->findNet("quad_sum\\[0\\]\\[524\\]");auto* base=tech->findVia("VIA56");
    if(!edge || !edge->getWire() || edge->getWire()->length()!=143 || !base || block->findVia("T10_S29_VIA56_M5_W120"))
      throw std::runtime_error("unexpected net524 input");
    auto* er=reinterpret_cast<odb::_dbWire*>(edge->getWire());unsigned found=0,index=0;
    for(unsigned i=1;i<143;++i) {
      if((er->opcodes_[i]&WOP_OPCODE_MASK)!=odb::kTechVia || er->data_[i]!=static_cast<int>(base->getId()))continue;
      odb::WirePoint p;odb::getPrevPoint(tech,block,er->opcodes_,er->data_,i-1,false,p);
      if(p.x==136956 && p.y==414032) {++found;index=i;}
    }
    if(found!=1)throw std::runtime_error("net524 via absent/ambiguous");
    found=0;
    for(auto* b:base->getBoxes())if(b->getTechLayer()->getName()=="M5") {
      if(std::array<int,4>{b->xMin(),b->yMin(),b->xMax(),b->yMax()}!=std::array<int,4>{-12,-27,12,27})
        throw std::runtime_error("unexpected net524 via plate");
      ++found;
    }
    if(found!=1)throw std::runtime_error("unexpected net524 plate count");
    auto* v=odb::dbVia::create(block,"T10_S29_VIA56_M5_W120");
    for(auto* b:base->getBoxes()) {
      bool edit=b->getTechLayer()->getName()=="M5";
      odb::dbBox::create(v,b->getTechLayer(),edit?-60:b->xMin(),edit?-16:b->yMin(),edit?60:b->xMax(),edit?16:b->yMax());
    }
    er->opcodes_[index]=(er->opcodes_[index]&~WOP_OPCODE_MASK)|odb::kVia;er->data_[index]=v->getId();
    enc.append(edge->getWire());enc.newPath(tech->findLayer("M5"),odb::dbWireType::ROUTED);
    enc.addPoint(136956,414032);enc.addRect(-60,-16,60,195);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net569 bounded bridge; net524 straight 120x211nm M5 rectangle",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int shift19568(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_shift19568");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();
    auto* net=block->findNet("net19568");
    if(!net || !net->getWire() || net->getWire()->length()!=464)throw std::runtime_error("unexpected net19568 wire");
    auto* wire=net->getWire();auto* raw=reinterpret_cast<odb::_dbWire*>(wire);
    unsigned count=0;std::vector<int> ys;
    for(unsigned i=0;i<wire->length();++i) {
      auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
      if((raw->opcodes_[i]&WOP_OPCODE_MASK)==odb::kX && raw->data_[i]==316496)++count;
      if(op==odb::kTechVia && raw->data_[i]==static_cast<int>(db->getTech()->findVia("VIA67")->getId())) {
        odb::WirePoint p;odb::getPrevPoint(db->getTech(),block,raw->opcodes_,raw->data_,i-1,false,p);
        if(p.x==316496)ys.push_back(p.y);
      }
    }
    if(count!=5 || ys.size()!=2 || !((ys[0]==299920 && ys[1]==329616) || (ys[1]==299920 && ys[0]==329616)))
      throw std::runtime_error("unexpected net19568 column encoding");
    for(unsigned i=0;i<wire->length();++i)
      if((raw->opcodes_[i]&WOP_OPCODE_MASK)==odb::kX && raw->data_[i]==316496)raw->data_[i]=316560;
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net19568 M7 column +64nm; five coordinates; via cuts unchanged",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int bridge461(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_bridge461");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[461\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=271)throw std::runtime_error("unexpected net461 wire");
    auto* wire=net->getWire();auto* raw=reinterpret_cast<odb::_dbWire*>(wire);
    std::vector<unsigned> starts;std::map<unsigned,std::vector<odb::dbShape>> shapes;
    for(unsigned i=0;i<271;++i) {
      auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kPath)starts.push_back(i);
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    starts.push_back(271);odb::dbWireShapeItr it;odb::dbShape shape;it.begin(wire);
    while(it.next(shape)) {
      unsigned start=0;for(auto p:starts) {if(p>it.getShapeId())break;start=p;}shapes[start].push_back(shape);
    }
    std::vector<unsigned> selected;
    for(unsigned k=0;k+1<starts.size();++k) {
      auto begin=starts[k],end=starts[k+1];bool inside=!shapes[begin].empty();
      for(auto s:shapes[begin]) {auto b=s.getBox();inside&=b.xMin()>=363070 && b.yMin()>=284800 && b.xMax()<=365280 && b.yMax()<=284970;}
      for(unsigned i=begin;i<end;++i)if((raw->opcodes_[i]&WOP_OPCODE_MASK)==odb::kIterm || (raw->opcodes_[i]&WOP_OPCODE_MASK)==odb::kBterm)inside=false;
      if(inside) {if(end!=begin+5)throw std::runtime_error("non-isolated path");selected.push_back(begin);}
    }
    if(selected!=std::vector<unsigned>{121,126,256,261,266})throw std::runtime_error("unexpected net461 cut");
    for(auto begin:selected)for(unsigned i=begin;i<begin+5;++i) {raw->opcodes_[i]=odb::kNop;raw->data_[i]=0;}
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);
    };
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));
    };
    segment("M5",360924,284944,360924,284988);
    segment("M6",360924,284944,361616,284944);
    segment("M7",361616,284944,361616,291280);
    segment("M6",361616,291280,365820,291280);
    segment("M5",365820,284940,365820,291280);
    via("M4","VIA45",360924,284988);via("M5","VIA56",360924,284944);
    via("M6","VIA67",361616,284944);via("M6","VIA67",361616,291280);
    via("M5","VIA56",365820,291280);via("M4","VIA45",365820,284940);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net461 bounded five-path removal and five-segment bridge",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int inspect19568(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  if(argc!=1)return 1;
  auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();
  auto* target=block->findNet("net19568");auto* layer=db->getTech()->findLayer("M7");
  std::array<int,3> columns={316560,316624,316688};std::array<unsigned,3> counts={0,0,0};
  std::ostringstream out;out<<"READ_ONLY M7 metal clearance study, not DRC qualification\n";
  auto check=[&](const odb::Rect& b,const std::string& source) {
    for(unsigned i=0;i<columns.size();++i) {
      int required=std::min(b.dx(),b.dy())>32?72:32;
      int gap=std::max({b.xMin()-(columns[i]+16),columns[i]-16-b.xMax(),b.yMin()-329643,299893-b.yMax(),0});
      if(gap<required) {
        if(counts[i]<5)out<<"x="<<columns[i]<<" conflict "<<source<<" "<<b.xMin()<<","<<b.yMin()<<","<<b.xMax()<<","<<b.yMax()<<" gap="<<gap<<"\n";
        ++counts[i];
      }
    }
  };
  for(auto* n:block->getNets()) {
    if(n==target)continue;
    if(n->getWire()) {
      odb::dbWireShapeItr it;odb::dbShape s;it.begin(n->getWire());
      while(it.next(s)) {
        if(!s.isVia()) {if(s.getTechLayer()==layer)check(s.getBox(),n->getName());continue;}
        auto pos=s.getViaXY();
        auto boxes=s.getTechVia()?s.getTechVia()->getBoxes():s.getVia()->getBoxes();
        for(auto* b:boxes)if(b->getTechLayer()==layer)
          check(odb::Rect(b->xMin()+pos.x(),b->yMin()+pos.y(),b->xMax()+pos.x(),b->yMax()+pos.y()),n->getName());
      }
    }
    for(auto* sw:n->getSWires())for(auto* b:sw->getWires()) {
      if(!b->isVia()) {if(b->getTechLayer()==layer)check(b->getBox(),n->getName());}
      else {std::vector<odb::dbShape> parts;b->getViaBoxes(parts);for(auto& s:parts)if(s.getTechLayer()==layer)check(s.getBox(),n->getName());}
    }
  }
  for(auto* inst:block->getInsts())for(auto* b:inst->getMaster()->getObstructions())if(b->getTechLayer()==layer) {
    auto rect=b->getBox();auto transform=inst->getTransform();transform.apply(rect);check(rect,inst->getName());
  }
  for(auto* ob:block->getObstructions())if(ob->getBBox()->getTechLayer()==layer)check(ob->getBBox()->getBox(),"block_OBS");
  for(unsigned i=0;i<columns.size();++i)out<<"COLUMN "<<columns[i]<<" conflicts="<<counts[i]<<"\n";
  Tcl_SetObjResult(interp,Tcl_NewStringObj(out.str().c_str(),-1));return 0;
}
int stack571(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_stack571");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[571\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=443)throw std::runtime_error("unexpected net571 wire");
    auto* wire=net->getWire();auto* raw=reinterpret_cast<odb::_dbWire*>(wire);
    auto* original=tech->findVia("VIA45");unsigned index=0,count=0,endpoint=0,ends=0;
    for(unsigned i=1;i<443;++i)if((raw->opcodes_[i]&WOP_OPCODE_MASK)==odb::kTechVia && raw->data_[i]==static_cast<int>(original->getId())) {
      odb::WirePoint p;odb::getPrevPoint(tech,block,raw->opcodes_,raw->data_,i-1,false,p);
      if(p.x==364956 && p.y==284028) {index=i;++count;}
    }
    odb::dbWireShapeItr it;odb::dbShape shape;it.begin(wire);
    while(it.next(shape))if(!shape.isVia() && shape.getTechLayer()->getName()=="M4") {
      auto b=shape.getBox();
      if(std::array<int,4>{b.xMin(),b.yMin(),b.xMax(),b.yMax()}==std::array<int,4>{362841,284016,364968,284040}) {endpoint=it.getShapeId();++ends;}
    }
    if(count!=1 || ends!=1 || (raw->opcodes_[endpoint]&WOP_OPCODE_MASK)!=odb::kX || raw->data_[endpoint]!=364956)
      throw std::runtime_error("unexpected net571 attachment geometry");
    auto rotate=[&](const char* name,const char* base,std::array<int,4> expected) {
      if(block->findVia(name))throw std::runtime_error("stack already exists");
      auto* v=tech->findVia(base);unsigned found=0;
      for(auto* b:v->getBoxes())if(b->getTechLayer()->getName()=="M4") {
        if(std::array<int,4>{b->xMin(),b->yMin(),b->xMax(),b->yMax()}!=expected)throw std::runtime_error("unexpected stack plate");++found;
      }
      if(found!=1)throw std::runtime_error("unexpected plate count");
      auto* result=odb::dbVia::create(block,name);
      for(auto* b:v->getBoxes()) {bool edit=b->getTechLayer()->getName()=="M4";
        odb::dbBox::create(result,b->getTechLayer(),edit?-12:b->xMin(),edit?-23:b->yMin(),edit?12:b->xMax(),edit?23:b->yMax());}
      return result;
    };
    auto* v45=rotate("T10_S29_571_VIA45_STACK","VIA45",{-23,-12,23,12});
    auto* v34=rotate("T10_S29_571_VIA34_STACK","VIA34",{-20,-12,20,12});
    raw->data_[endpoint]=364833;raw->opcodes_[index]=(raw->opcodes_[index]&~WOP_OPCODE_MASK)|odb::kVia;raw->data_[index]=v45->getId();
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);};
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));};
    segment("M3",364833,283956,364833,284028);segment("M2",364833,283956,364956,283956);segment("M3",364956,283956,364956,284028);
    via("M3","VIA34",364833,284028);via("M2","VIA23",364833,283956);via("M2","VIA23",364956,283956);
    enc.newPath(tech->findLayer("M3"),odb::dbWireType::ROUTED);enc.addPoint(364956,284028);enc.addVia(v34);
    enc.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);enc.addPoint(364956,284028);enc.addRect(-12,-42,12,42);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net571 M4 rectangular stack, unchanged M5 column, M2/M3 feed",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int shift559(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_shift559");
    auto* block=ord::OpenRoad::openRoad()->getDb()->getChip()->getBlock();
    auto* net=block->findNet("quad_sum\\[3\\]\\[559\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=636)throw std::runtime_error("unexpected net559 wire");
    auto* raw=reinterpret_cast<odb::_dbWire*>(net->getWire());
    const std::array<std::pair<unsigned,int>,10> edits={{{274,365229},{277,365229},{282,365229},
      {284,365301},{287,365301},{297,365301},{582,365229},{587,365229},{592,365301},{597,365301}}};
    for(auto [i,before]:edits)if((raw->opcodes_[i]&WOP_OPCODE_MASK)!=odb::kX || raw->data_[i]!=before)
      throw std::runtime_error("unexpected net559 attachment encoding");
    const std::array<unsigned,7> ops={odb::kPath,odb::kX,odb::kY,odb::kRect,odb::kOperand,odb::kOperand,odb::kOperand};
    const std::array<int,7> data={18,365229,284988,-59,-12,-20,12};
    for(unsigned i=0;i<7;++i)if((raw->opcodes_[629+i]&WOP_OPCODE_MASK)!=ops[i] || raw->data_[629+i]!=data[i])
      throw std::runtime_error("unexpected net559 RECT");
    for(unsigned i=0;i<636;++i) {
      auto op=raw->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    // Center the bridge between the two fixed M4 line ends: both gaps 50nm.
    for(auto [i,before]:edits)raw->data_[i]=before+18;
    for(unsigned i=629;i<636;++i) {raw->opcodes_[i]=odb::kNop;raw->data_[i]=0;}
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net559 local bridge +18nm; remove redundant RECT; cuts retain 72nm pitch",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int bridge473(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_bridge473");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[473\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=407)throw std::runtime_error("unexpected net473 wire");
    auto* wire=net->getWire();auto* r=reinterpret_cast<odb::_dbWire*>(wire);
    const std::array<unsigned,5> segmentOps={odb::kPath,odb::kX,odb::kY,odb::kY,odb::kProperty};
    const std::array<int,5> segmentData={16,362889,284769,285039,0};
    for(unsigned k=0;k<5;++k)if((r->opcodes_[146+k]&WOP_OPCODE_MASK)!=segmentOps[k] || r->data_[146+k]!=segmentData[k])
      throw std::runtime_error("unexpected net473 column");
    for(auto [start,y]:std::array<std::pair<unsigned,int>,2>{{{346,284769},{351,285039}}}) {
      if((r->opcodes_[start]&WOP_OPCODE_MASK)!=odb::kPath || r->data_[start]!=14 ||
         (r->opcodes_[start+1]&WOP_OPCODE_MASK)!=odb::kX || r->data_[start+1]!=362889 ||
         (r->opcodes_[start+2]&WOP_OPCODE_MASK)!=odb::kY || r->data_[start+2]!=y ||
         (r->opcodes_[start+3]&WOP_OPCODE_MASK)!=odb::kTechVia || r->data_[start+3]!=static_cast<int>(tech->findVia("VIA23")->getId()) ||
         (r->opcodes_[start+4]&WOP_OPCODE_MASK)!=odb::kColor)throw std::runtime_error("unexpected net473 attachment via");
    }
    for(unsigned i=0;i<407;++i) {
      auto op=r->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    for(unsigned start:{146,346,351})for(unsigned i=start;i<start+5;++i) {r->opcodes_[i]=odb::kNop;r->data_[i]=0;}
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);};
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));};
    segment("M3",362853,284463,362853,284769);segment("M2",362709,284463,362853,284463);
    segment("M3",362709,284268,362709,284463);segment("M4",361593,284268,362709,284268);
    segment("M3",361593,283548,361593,284268);segment("M4",361593,283548,363180,283548);
    segment("M5",363180,283548,363180,283664);segment("M6",363180,283664,363216,283664);
    segment("M7",363216,283664,363216,284752);segment("M6",363180,284752,363216,284752);
    segment("M5",363180,284752,363180,285132);segment("M4",362889,285132,363180,285132);
    segment("M3",362889,285039,362889,285132);
    via("M2","VIA23",362853,284769);via("M2","VIA23",362853,284463);via("M2","VIA23",362709,284463);
    via("M3","VIA34",362709,284268);via("M3","VIA34",361593,284268);via("M3","VIA34",361593,283548);
    via("M4","VIA45",363180,283548);via("M5","VIA56",363180,283664);via("M6","VIA67",363216,283664);
    via("M6","VIA67",363216,284752);via("M5","VIA56",363180,284752);via("M4","VIA45",363180,285132);
    via("M3","VIA34",362889,285132);via("M2","VIA23",362889,285039);
    // Extend the straight M4 rectangle into lateral overlap with net526.
    // This removes a 2nm diagonal corner offset while retaining 24nm spacing.
    enc.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);
    enc.addPoint(361593,283548);enc.addRect(-44,-12,-20,12);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net473 bounded signal-only detour; VDD special routing unchanged",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int bridge301(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_bridge301");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[301\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=492)throw std::runtime_error("unexpected net301 wire");
    auto* wire=net->getWire();auto* r=reinterpret_cast<odb::_dbWire*>(wire);
    auto guard=[&](unsigned start,const std::vector<unsigned>& ops,const std::vector<int>& data) {
      for(unsigned i=0;i<ops.size();++i)if((r->opcodes_[start+i]&WOP_OPCODE_MASK)!=ops[i] || r->data_[start+i]!=data[i])
        throw std::runtime_error("unexpected net301 fragment encoding");
    };
    guard(226,{odb::kPath,odb::kX,odb::kY,odb::kX,odb::kProperty},{18,344313,284748,365004,0});
    guard(211,{odb::kPath,odb::kX,odb::kY,odb::kY,odb::kProperty},{20,365004,284748,286140,0});
    auto viaId=static_cast<int>(tech->findVia("VIA45")->getId());
    guard(451,{odb::kPath,odb::kX,odb::kY,odb::kTechVia,odb::kColor},{18,365004,284748,viaId,0});
    guard(456,{odb::kPath,odb::kX,odb::kY,odb::kTechVia,odb::kColor},{18,365004,286140,viaId,0});
    guard(461,{odb::kPath,odb::kX,odb::kY,odb::kTechVia,odb::kColor},{18,365100,286140,viaId,0});
    guard(478,{odb::kPath,odb::kX,odb::kY,odb::kRect,odb::kOperand,odb::kOperand,odb::kOperand},{18,365004,284748,23,-12,37,12});
    guard(485,{odb::kPath,odb::kX,odb::kY,odb::kRect,odb::kOperand,odb::kOperand,odb::kOperand},{20,365004,284748,-12,-38,12,-23});
    for(unsigned i=0;i<492;++i) {
      auto op=r->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    for(auto [start,end]:std::array<std::pair<unsigned,unsigned>,5>{{{211,216},{451,456},{456,461},{478,485},{485,492}}})
      for(unsigned i=start;i<end;++i) {r->opcodes_[i]=odb::kNop;r->data_[i]=0;}
    r->data_[229]=364833;
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);};
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));};
    segment("M5",361164,284748,361164,284752);segment("M6",361164,284752,362128,284752);
    segment("M7",362128,284752,362128,291344);segment("M6",362128,291344,365100,291344);
    segment("M5",365100,286140,365100,291344);
    via("M4","VIA45",361164,284748);via("M5","VIA56",361164,284752);via("M6","VIA67",362128,284752);
    via("M6","VIA67",362128,291344);via("M5","VIA56",365100,291344);
    // The retained destination VIA45 at (365100,286140) already joins M4/M5.
    enc.newPath(tech->findLayer("M5"),odb::dbWireType::ROUTED);enc.addPoint(361164,284752);enc.addRect(-12,-42,12,42);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net301 corner fragment replacement; incoming M4 shortened; destination via retained",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
int bridge465(ClientData,Tcl_Interp* interp,int argc,Tcl_Obj* const[]) {
  try {
    if(argc!=1)throw std::runtime_error("usage: t10_seed29_bridge465");
    auto* db=ord::OpenRoad::openRoad()->getDb();auto* block=db->getChip()->getBlock();auto* tech=db->getTech();
    auto* net=block->findNet("quad_sum\\[3\\]\\[465\\]");
    if(!net || !net->getWire() || net->getWire()->length()!=318)throw std::runtime_error("unexpected net465 wire");
    auto* wire=net->getWire();auto* r=reinterpret_cast<odb::_dbWire*>(wire);
    auto guard=[&](unsigned start,const std::vector<unsigned>& ops,const std::vector<int>& data) {
      for(unsigned i=0;i<ops.size();++i)if((r->opcodes_[start+i]&WOP_OPCODE_MASK)!=ops[i] || r->data_[start+i]!=data[i])
        throw std::runtime_error("unexpected net465 fragment encoding");
    };
    guard(131,{odb::kPath,odb::kX,odb::kY,odb::kY,odb::kProperty},{16,364761,283005,284733,0});
    guard(141,{odb::kPath,odb::kX,odb::kY,odb::kY,odb::kProperty},{16,365049,284733,287631,0});
    guard(146,{odb::kPath,odb::kX,odb::kY,odb::kX,odb::kProperty},{14,364761,284733,365049,0});
    auto id=static_cast<int>(tech->findVia("VIA23")->getId());
    for(auto data:std::array<std::array<int,3>,5>{{{286,364077,283005},{291,364761,283005},{296,364761,284733},{301,365049,284733},{306,365049,287631}}})
      guard(data[0],{odb::kPath,odb::kX,odb::kY,odb::kTechVia,odb::kColor},{14,data[1],data[2],id,0});
    for(unsigned i=0;i<318;++i) {
      auto op=r->opcodes_[i]&WOP_OPCODE_MASK;
      if(op==odb::kJunction || op==odb::kShort || op==odb::kVwire)throw std::runtime_error("cross-path reference");
    }
    for(unsigned start:{131,141,146,291,296,301,306})for(unsigned i=start;i<start+5;++i) {r->opcodes_[i]=odb::kNop;r->data_[i]=0;}
    odb::dbWireEncoder enc;enc.append(wire);
    auto segment=[&](const char* layer,int x0,int y0,int x1,int y1) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x0,y0);enc.addPoint(x1,y1);};
    auto via=[&](const char* layer,const char* name,int x,int y) {
      enc.newPath(tech->findLayer(layer),odb::dbWireType::ROUTED);enc.addPoint(x,y);enc.addTechVia(tech->findVia(name));};
    segment("M3",364077,283005,364077,283548);segment("M4",363948,283548,364077,283548);
    segment("M5",363948,283548,363948,284112);segment("M6",363088,284112,363948,284112);
    segment("M7",363088,284112,363088,286864);segment("M6",363088,286864,363468,286864);
    segment("M5",363468,286864,363468,290172);segment("M4",363468,290172,363933,290172);
    segment("M3",363933,290172,363933,290331);segment("M2",363933,290331,364149,290331);
    segment("M3",364149,290331,364149,290871);segment("M2",364149,290871,365985,290871);
    segment("M3",365985,287631,365985,290871);
    // Retain the existing source VIA23 at (364077,283005), without duplication.
    via("M3","VIA34",364077,283548);via("M4","VIA45",363948,283548);via("M5","VIA56",363948,284112);
    via("M6","VIA67",363088,284112);via("M6","VIA67",363088,286864);via("M5","VIA56",363468,286864);
    via("M4","VIA45",363468,290172);via("M3","VIA34",363933,290172);via("M2","VIA23",363933,290331);
    via("M2","VIA23",364149,290331);via("M2","VIA23",364149,290871);via("M2","VIA23",365985,290871);
    via("M2","VIA23",365985,287631);
    // Preserve one straight rectangle while eliminating the diagonal M4
    // corner relation to net478; lateral spacing remains 24nm.
    enc.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);
    enc.addPoint(363933,290172);enc.addRect(20,-12,76,12);enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("APPLIED net465 bounded bridge; macro boundary and power grid unchanged",-1));return 0;
  } catch(const std::exception& e) {Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1));return 1;}
}
}
extern "C" int T10secondary_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_seed29_secondary",apply,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_shift19568",shift19568,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_inspect19568",inspect19568,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_stack571",stack571,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_shift559",shift559,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_bridge473",bridge473,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_bridge301",bridge301,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_bridge465",bridge465,nullptr,nullptr);
  Tcl_CreateObjCommand(interp,"t10_seed29_bridge461",bridge461,nullptr,nullptr);return 0;
}
