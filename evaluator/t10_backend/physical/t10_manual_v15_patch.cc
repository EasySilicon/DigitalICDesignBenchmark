#include <cstdint>
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

struct Edit
{
  const char* net;
  uint32_t wire_length;
  unsigned char opcode;
  int before;
  int after;
  int expected_count;
};

const std::vector<Edit> edits = {
    {"net24982", 226, 68, 365013, 364977, 5},
    {"level0\\[4\\]\\[314\\]", 284, 69, 406467, 406503, 5},
    {"net22071", 417, 68, 209916, 209868, 5},
    {"quad_sum\\[0\\]\\[355\\]", 101, 69, 414032, 414080, 5},
    {"quad_sum\\[1\\]\\[366\\]", 438, 68, 316496, 316624, 5},
};

int patch(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const objv[])
{
  if (objc != 2) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj("usage: t10_manual_v15_patch case_number", -1));
    return TCL_ERROR;
  }
  int selected = 0;
  if (Tcl_GetIntFromObj(interp, objv[1], &selected) != TCL_OK) return TCL_ERROR;
  if (selected != 5) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj("only case 5 has a verified free replacement track", -1));
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

    // Validate the complete edit set before changing any byte.
    for (const Edit& edit : edits) {
      if (&edit != &edits[selected - 1]) continue;
      auto* net = block->findNet(edit.net);
      if (net == nullptr || net->getWire() == nullptr) {
        throw std::runtime_error(std::string("missing routed net ") + edit.net);
      }
      auto* wire = net->getWire();
      if (wire->length() != edit.wire_length) {
        std::ostringstream message;
        message << edit.net << ": expected wire length " << edit.wire_length
                << ", got " << wire->length();
        throw std::runtime_error(message.str());
      }
      auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
      int count = 0;
      for (uint32_t index = 0; index < wire->length(); ++index) {
        if (raw->opcodes_[index] == edit.opcode
            && raw->data_[index] == edit.before) {
          ++count;
        }
      }
      if (count != edit.expected_count) {
        std::ostringstream message;
        message << edit.net << ": expected " << edit.expected_count
                << " opcode/data matches, got " << count;
        throw std::runtime_error(message.str());
      }
    }

    int changed = 0;
    for (const Edit& edit : edits) {
      if (&edit != &edits[selected - 1]) continue;
      auto* wire = block->findNet(edit.net)->getWire();
      auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
      for (uint32_t index = 0; index < wire->length(); ++index) {
        if (raw->opcodes_[index] == edit.opcode
            && raw->data_[index] == edit.before) {
          raw->data_[index] = edit.after;
          ++changed;
        }
      }
    }

    std::ostringstream result;
    result << "nets=1 case=" << selected << " coordinates_changed=" << changed;
    Tcl_SetObjResult(interp, Tcl_NewStringObj(result.str().c_str(), -1));
    return TCL_OK;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj(error.what(), -1));
    return TCL_ERROR;
  }
}
}  // namespace

extern "C" int T10manualv15patch_Init(Tcl_Interp* interp)
{
  Tcl_CreateObjCommand(
      interp, "t10_manual_v15_patch", patch, nullptr, nullptr);
  return TCL_OK;
}
