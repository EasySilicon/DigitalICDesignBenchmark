#include <exception>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "dbWire.h"
#include "odb/db.h"
#include "ord/OpenRoad.hh"
struct Tcl_Interp; struct Tcl_Obj; using ClientData=void*;
using Tcl_ObjCmdProc=int(ClientData,Tcl_Interp*,int,Tcl_Obj* const[]);
extern "C" { void* Tcl_CreateObjCommand(Tcl_Interp*,const char*,Tcl_ObjCmdProc*,ClientData,void(*)(ClientData)); Tcl_Obj* Tcl_NewStringObj(const char*,int); void Tcl_SetObjResult(Tcl_Interp*,Tcl_Obj*); int Tcl_GetIntFromObj(Tcl_Interp*,Tcl_Obj*,int*); }
namespace {
constexpr int TCL_OK=0,TCL_ERROR=1;
struct M{int i;unsigned char op;int before;int after;};
void mutate(odb::dbBlock* b,const char* n,uint32_t len,const std::vector<M>& cs){auto* net=b->findNet(n);if(!net||!net->getWire()||net->getWire()->length()!=len)throw std::runtime_error(std::string("unexpected routed net ")+n);auto* r=reinterpret_cast<odb::_dbWire*>(net->getWire());for(auto& c:cs)if(r->opcodes_[c.i]!=c.op||r->data_[c.i]!=c.before)throw std::runtime_error(std::string(n)+" unexpected opcode/data");for(auto& c:cs)r->data_[c.i]=c.after;}
int patch(ClientData,Tcl_Interp* t,int objc,Tcl_Obj* const o[]){if(objc!=3){Tcl_SetObjResult(t,Tcl_NewStringObj("usage: patch_cluster04_wire_opcodes dx_left dx_right",-1));return TCL_ERROR;}int a=0,b=0;if(Tcl_GetIntFromObj(t,o[1],&a)!=TCL_OK||Tcl_GetIntFromObj(t,o[2],&b)!=TCL_OK)return TCL_ERROR;try{auto* block=ord::OpenRoad::openRoad()->getDb()->getChip()->getBlock();mutate(block,"core/net7108",725,{{273,68,290637,290637+a},{276,68,290637,290637+a},{281,68,290637,290637+a},{641,68,290637,290637+a},{646,68,290637,290637+a},{719,68,290637,290637+a}});mutate(block,"core/net7105",767,{{13,68,310761,310761+b},{16,68,310761,310761+b},{331,68,310761,310761+b},{366,68,310761,310761+b},{371,68,310761,310761+b},{698,68,310761,310761+b}});std::ostringstream s;s<<"patched=12 dx_left="<<a<<" dx_right="<<b;Tcl_SetObjResult(t,Tcl_NewStringObj(s.str().c_str(),-1));return TCL_OK;}catch(const std::exception& e){Tcl_SetObjResult(t,Tcl_NewStringObj(e.what(),-1));return TCL_ERROR;}}
}
extern "C" int Patchcluster04wireopcodes_Init(Tcl_Interp* t){Tcl_CreateObjCommand(t,"patch_cluster04_wire_opcodes",patch,nullptr,nullptr);return TCL_OK;}
