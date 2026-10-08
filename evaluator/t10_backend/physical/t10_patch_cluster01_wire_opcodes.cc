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
  odb::dbNet* net = block->findNet(name);
  if (net == nullptr || net->getWire() == nullptr) {
    throw std::runtime_error(std::string("missing routed net ") + name);
  }
  odb::dbWire* wire = net->getWire();
  if (wire->length() != expected_length) {
    std::ostringstream message;
    message << name << ": expected wire length " << expected_length << ", got "
            << wire->length();
    throw std::runtime_error(message.str());
  }
  auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
  for (const Mutation& mutation : mutations) {
    if (mutation.index < 0
        || mutation.index >= static_cast<int>(wire->length())) {
      throw std::runtime_error(std::string(name) + ": mutation index out of range");
    }
    const unsigned char opcode = raw->opcodes_[mutation.index];
    const int data = raw->data_[mutation.index];
    if (opcode != mutation.opcode || data != mutation.before) {
      std::ostringstream message;
      message << name << " index " << mutation.index << ": expected opcode/data "
              << static_cast<int>(mutation.opcode) << "/" << mutation.before
              << ", got " << static_cast<int>(opcode) << "/" << data;
      throw std::runtime_error(message.str());
    }
  }
  for (const Mutation& mutation : mutations) {
    raw->data_[mutation.index] = mutation.after;
  }
  for (const Mutation& mutation : mutations) {
    if (raw->opcodes_[mutation.index] != mutation.opcode
        || raw->data_[mutation.index] != mutation.after) {
      throw std::runtime_error(std::string(name) + ": post-mutation audit failed");
    }
  }
}

int patchCluster01(ClientData,
                   Tcl_Interp* interp,
                   int objc,
                   Tcl_Obj* const[])
{
  if (objc != 1) {
    Tcl_SetObjResult(
        interp, Tcl_NewStringObj("usage: patch_cluster01_wire_opcodes", -1));
    return TCL_ERROR;
  }
  try {
    ord::OpenRoad* app = ord::OpenRoad::openRoad();
    if (app == nullptr || app->getDb() == nullptr
        || app->getDb()->getChip() == nullptr
        || app->getDb()->getChip()->getBlock() == nullptr) {
      throw std::runtime_error("OpenDB block is unavailable");
    }
    odb::dbBlock* block = app->getDb()->getChip()->getBlock();
    odb::dbTech* tech = app->getDb()->getTech();
    if (tech->findLayer("M4")->getId() != 18
        || tech->findLayer("M5")->getId() != 20
        || tech->findLayer("M6")->getId() != 22
        || tech->findVia("VIA45")->getId() != 6
        || tech->findVia("VIA56")->getId() != 5) {
      throw std::runtime_error("unexpected ASAP7 layer/via object IDs");
    }

    // Replace net6243's M4 bridge at y=203052 with an M6 bridge at y=203088,
    // and convert its two VIA45 endpoints to VIA56.  All path structure and
    // every nonlisted opcode remain untouched.
    mutateNet(block,
              "core/net6243",
              286,
              {{75, 96, 18, 22},
               {77, 69, 203052, 203088},
               {225, 96, 18, 20},
               {227, 69, 203052, 203088},
               {228, 136, 6, 5},
               {230, 96, 18, 20},
               {232, 69, 203052, 203088},
               {233, 136, 6, 5}});

    // Move net8483's M4 crossbar and its two M3/VIA34 endpoints down four M4
    // tracks, away from net8496.
    mutateNet(block,
              "core/net8483",
              745,
              {{264, 69, 211452, 211260},
               {268, 69, 211452, 211260},
               {273, 69, 211452, 211260},
               {648, 69, 211452, 211260},
               {653, 69, 211452, 211260}});

    // Raise net8554's local M4 bridge one track so the new net6243 VIA56 at
    // y=203088 has legal M5 spacing.
    mutateNet(block,
              "core/net8554",
              367,
              {{134, 69, 203148, 203196},
               {138, 69, 203148, 203196},
               {143, 69, 203148, 203196},
               {328, 69, 203148, 203196},
               {333, 69, 203148, 203196}});

    Tcl_SetObjResult(
        interp,
        Tcl_NewStringObj(
            "patched=18 nets=core/net6243,core/net8483,core/net8554", -1));
    return TCL_OK;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj(error.what(), -1));
    return TCL_ERROR;
  }
}
}  // namespace

extern "C" int Patchcluster01wireopcodes_Init(Tcl_Interp* interp)
{
  Tcl_CreateObjCommand(interp,
                       "patch_cluster01_wire_opcodes",
                       patchCluster01,
                       nullptr,
                       nullptr);
  return TCL_OK;
}
