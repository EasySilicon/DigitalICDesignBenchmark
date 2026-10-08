#include <algorithm>
#include <cstdint>
#include <exception>
#include <fstream>
#include <iomanip>
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
const char* Tcl_GetString(Tcl_Obj*);
}

namespace {
constexpr int TCL_OK = 0;
constexpr int TCL_ERROR = 1;

uint64_t fnvByte(uint64_t hash, uint8_t value)
{
  return (hash ^ value) * 1099511628211ULL;
}

uint64_t wireHash(odb::dbWire* wire)
{
  constexpr uint64_t offset = 14695981039346656037ULL;
  uint64_t hash = offset;
  auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
  for (uint32_t i = 0; i < wire->length(); ++i) {
    hash = fnvByte(hash, raw->opcodes_[i]);
    const uint32_t value = static_cast<uint32_t>(raw->data_[i]);
    for (int byte = 0; byte < 4; ++byte) {
      hash = fnvByte(hash, (value >> (8 * byte)) & 0xff);
    }
  }
  return hash;
}

int auditWireRaw(ClientData,
                 Tcl_Interp* interp,
                 int objc,
                 Tcl_Obj* const objv[])
{
  if (objc != 2) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj("usage: audit_wire_raw output", -1));
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
    std::vector<odb::dbNet*> nets;
    for (auto* net : block->getNets()) {
      if (net->getWire() != nullptr) {
        nets.push_back(net);
      }
    }
    std::sort(nets.begin(), nets.end(), [](auto* lhs, auto* rhs) {
      return std::string(lhs->getConstName()) < std::string(rhs->getConstName());
    });

    std::ofstream out(Tcl_GetString(objv[1]));
    if (!out) {
      throw std::runtime_error("cannot open audit output");
    }
    out << "HASHES\n";
    for (auto* net : nets) {
      auto* wire = net->getWire();
      out << net->getConstName() << ' ' << wire->length() << ' ' << std::hex
          << std::setw(16) << std::setfill('0') << wireHash(wire) << std::dec
          << '\n';
    }
    out << "DETAILS\n";
    for (const char* name : {"core/net6243", "core/net8483", "core/net8554"}) {
      auto* net = block->findNet(name);
      if (net == nullptr || net->getWire() == nullptr) {
        throw std::runtime_error(std::string("missing routed net ") + name);
      }
      auto* wire = net->getWire();
      auto* raw = reinterpret_cast<odb::_dbWire*>(wire);
      for (uint32_t i = 0; i < wire->length(); ++i) {
        out << name << ' ' << i << ' ' << static_cast<int>(raw->opcodes_[i])
            << ' ' << raw->data_[i] << '\n';
      }
    }
    out.close();
    std::ostringstream result;
    result << "nets=" << nets.size();
    Tcl_SetObjResult(interp, Tcl_NewStringObj(result.str().c_str(), -1));
    return TCL_OK;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj(error.what(), -1));
    return TCL_ERROR;
  }
}
}  // namespace

extern "C" int Auditwireraw_Init(Tcl_Interp* interp)
{
  Tcl_CreateObjCommand(
      interp, "audit_wire_raw", auditWireRaw, nullptr, nullptr);
  return TCL_OK;
}
