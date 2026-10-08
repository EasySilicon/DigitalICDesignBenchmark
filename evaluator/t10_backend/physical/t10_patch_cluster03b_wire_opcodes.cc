#include <exception>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "dbWire.h"
#include "odb/db.h"
#include "ord/OpenRoad.hh"

struct Tcl_Interp; struct Tcl_Obj;
using ClientData = void*;
using Tcl_ObjCmdProc = int(ClientData, Tcl_Interp*, int, Tcl_Obj* const[]);
extern "C" {
void* Tcl_CreateObjCommand(Tcl_Interp*, const char*, Tcl_ObjCmdProc*, ClientData,
                           void (*)(ClientData));
Tcl_Obj* Tcl_NewStringObj(const char*, int);
void Tcl_SetObjResult(Tcl_Interp*, Tcl_Obj*);
int Tcl_GetIntFromObj(Tcl_Interp*, Tcl_Obj*, int*);
}
namespace {
constexpr int TCL_OK=0, TCL_ERROR=1;
struct Mutation { int index; unsigned char opcode; int before; int after; };
void mutate(odb::dbBlock* block, const char* name, uint32_t length,
            const std::vector<Mutation>& changes)
{
  auto* net=block->findNet(name);
  if (!net || !net->getWire() || net->getWire()->length()!=length)
    throw std::runtime_error(std::string("unexpected routed net ")+name);
  auto* raw=reinterpret_cast<odb::_dbWire*>(net->getWire());
  for (const auto& c: changes) {
    if (raw->opcodes_[c.index]!=c.opcode || raw->data_[c.index]!=c.before) {
      std::ostringstream out; out<<name<<" index "<<c.index<<": unexpected opcode/data";
      throw std::runtime_error(out.str());
    }
  }
  for (const auto& c: changes) raw->data_[c.index]=c.after;
}
int patch(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const objv[])
{
  if (objc!=3) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(
      "usage: patch_cluster03b_wire_opcodes dx_eol dx_corner",-1));
    return TCL_ERROR;
  }
  int dx_eol=0,dx_corner=0;
  if (Tcl_GetIntFromObj(interp,objv[1],&dx_eol)!=TCL_OK ||
      Tcl_GetIntFromObj(interp,objv[2],&dx_corner)!=TCL_OK) return TCL_ERROR;
  try {
    auto* block=ord::OpenRoad::openRoad()->getDb()->getChip()->getBlock();
    mutate(block,"core/net6281",898,
      {{286,68,326961,326961+dx_eol},{291,68,326961,326961+dx_eol},
       {296,68,326961,326961+dx_eol},{716,68,326961,326961+dx_eol},
       {721,68,326961,326961+dx_eol},{878,68,326961,326961+dx_eol}});
    mutate(block,"core/float_pending_words\\[1\\]\\[206\\]",420,
      {{147,68,319221,319221+dx_corner},{152,68,319221,319221+dx_corner},
       {199,68,319221,319221+dx_corner},{357,68,319221,319221+dx_corner},
       {362,68,319221,319221+dx_corner},{414,68,319221,319221+dx_corner}});
    std::ostringstream out; out<<"patched=12 dx_eol="<<dx_eol<<" dx_corner="<<dx_corner;
    Tcl_SetObjResult(interp,Tcl_NewStringObj(out.str().c_str(),-1));
    return TCL_OK;
  } catch (const std::exception& e) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(e.what(),-1)); return TCL_ERROR;
  }
}
}
extern "C" int Patchcluster03bwireopcodes_Init(Tcl_Interp* interp)
{
  Tcl_CreateObjCommand(interp,"patch_cluster03b_wire_opcodes",patch,nullptr,nullptr);
  return TCL_OK;
}
