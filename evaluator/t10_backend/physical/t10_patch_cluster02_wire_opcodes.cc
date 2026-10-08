#include <exception>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "dbWire.h"
#include "odb/db.h"
#include "ord/OpenRoad.hh"

struct Tcl_Interp;
struct Tcl_Obj;
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
constexpr int TCL_OK = 0;
constexpr int TCL_ERROR = 1;

struct Mutation
{
  int index;
  unsigned char opcode;
  int before;
  int after;
};

void mutateNet(odb::dbBlock* block,
               const char* name,
               uint32_t expected_length,
               const std::vector<Mutation>& mutations)
{
  auto* net = block->findNet(name);
  if (net == nullptr || net->getWire() == nullptr) {
    throw std::runtime_error(std::string("missing routed net ") + name);
  }
  auto* wire = net->getWire();
  if (wire->length() != expected_length) {
    std::ostringstream message;
    message << name << ": expected wire length " << expected_length << ", got "
            << wire->length();
    throw std::runtime_error(message.str());
  }
  auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
  for (const auto& mutation : mutations) {
    if (mutation.index < 0
        || mutation.index >= static_cast<int>(wire->length())
        || raw->opcodes_[mutation.index] != mutation.opcode
        || raw->data_[mutation.index] != mutation.before) {
      std::ostringstream message;
      message << name << " index " << mutation.index
              << ": unexpected opcode/data";
      throw std::runtime_error(message.str());
    }
  }
  for (const auto& mutation : mutations) {
    raw->data_[mutation.index] = mutation.after;
  }
}

int patchCluster02(ClientData,
                   Tcl_Interp* interp,
                   int objc,
                   Tcl_Obj* const objv[])
{
  if (objc != 3) {
    Tcl_SetObjResult(interp,
                     Tcl_NewStringObj(
                         "usage: patch_cluster02_wire_opcodes dx_left dx_right",
                         -1));
    return TCL_ERROR;
  }
  int dx_left = 0;
  int dx_right = 0;
  if (Tcl_GetIntFromObj(interp, objv[1], &dx_left) != TCL_OK
      || Tcl_GetIntFromObj(interp, objv[2], &dx_right) != TCL_OK) {
    return TCL_ERROR;
  }
  try {
    auto* app = ord::OpenRoad::openRoad();
    if (app == nullptr || app->getDb() == nullptr
        || app->getDb()->getChip() == nullptr
        || app->getDb()->getChip()->getBlock() == nullptr) {
      throw std::runtime_error("OpenDB block is unavailable");
    }
    auto* block = app->getDb()->getChip()->getBlock();
    mutateNet(block,
              "core/level1_q\\[2\\]\\[543\\]",
              265,
              {{6, 68, 245205, 245205 + dx_left},
               {74, 68, 245205, 245205 + dx_left},
               {82, 68, 245205, 245205 + dx_left},
               {137, 68, 245205, 245205 + dx_left},
               {142, 68, 245205, 245205 + dx_left},
               {18, 68, 255861, 255861 + dx_right},
               {21, 68, 255861, 255861 + dx_right},
               {26, 68, 255861, 255861 + dx_right},
               {157, 68, 255861, 255861 + dx_right},
               {162, 68, 255861, 255861 + dx_right}});
    std::ostringstream result;
    result << "patched=10 dx_left=" << dx_left << " dx_right=" << dx_right;
    Tcl_SetObjResult(interp, Tcl_NewStringObj(result.str().c_str(), -1));
    return TCL_OK;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj(error.what(), -1));
    return TCL_ERROR;
  }
}
}  // namespace

extern "C" int Patchcluster02wireopcodes_Init(Tcl_Interp* interp)
{
  Tcl_CreateObjCommand(interp,
                       "patch_cluster02_wire_opcodes",
                       patchCluster02,
                       nullptr,
                       nullptr);
  return TCL_OK;
}
