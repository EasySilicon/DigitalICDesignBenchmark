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
namespace { constexpr int TCL_OK=0,TCL_ERROR=1; struct M{int i;unsigned char op;int before;int after;};
void mutate(odb::dbBlock* b,const char* n,uint32_t len,const std::vector<M>& cs){auto* net=b->findNet(n);if(!net||!net->getWire()||net->getWire()->length()!=len)throw std::runtime_error(std::string("unexpected routed net ")+n);auto* r=reinterpret_cast<odb::_dbWire*>(net->getWire());for(auto& c:cs)if(r->opcodes_[c.i]!=c.op||r->data_[c.i]!=c.before)throw std::runtime_error(std::string(n)+" unexpected opcode/data");for(auto& c:cs)r->data_[c.i]=c.after;}
int patch(ClientData,Tcl_Interp* t,int objc,Tcl_Obj* const o[]){if(objc!=2){Tcl_SetObjResult(t,Tcl_NewStringObj("usage: patch_cluster13_wire_opcodes dx",-1));return TCL_ERROR;}int dx=0;if(Tcl_GetIntFromObj(t,o[1],&dx)!=TCL_OK)return TCL_ERROR;try{auto* b=ord::OpenRoad::openRoad()->getDb()->getChip()->getBlock();mutate(b,"core/net7394",811,{{31,68,295281,295281+dx},{36,68,295281,295281+dx},{148,68,295281,295281+dx},{431,68,295281,295281+dx},{436,68,295281,295281+dx}});std::ostringstream s;s<<"patched=5 dx="<<dx;Tcl_SetObjResult(t,Tcl_NewStringObj(s.str().c_str(),-1));return TCL_OK;}catch(const std::exception& e){Tcl_SetObjResult(t,Tcl_NewStringObj(e.what(),-1));return TCL_ERROR;}} }
extern "C" int Patchcluster13wireopcodes_Init(Tcl_Interp* t){Tcl_CreateObjCommand(t,"patch_cluster13_wire_opcodes",patch,nullptr,nullptr);return TCL_OK;}
