// Two deterministic, instance-local V2 enclosure edits. No wire coordinates,
// cuts, macro obstructions, constraints, or technology rules are changed.
#include <array>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

#include "dbWire.h"
#include "dbWireOpcode.h"
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
struct Edit {
  const char* net;
  unsigned length;
  const char* via;
  int x, y;
  const char* layer;
  std::array<int, 4> before, after;
};
const std::vector<Edit> edits = {
    {"net24982", 226, "VIA23", 365013, 278181, "M2",
     {-14, -9, 14, 9}, {-14, -9, 9, 9}},
    {"level0\\[4\\]\\[314\\]", 284, "VIA23", 210825, 406467, "M3",
     {-9, -14, 9, 14}, {-9, -9, 9, 14}},
};

int patch(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const[]) {
  try {
    if (objc != 1) throw std::runtime_error("usage: t10_manual_v15_enclosure");
    auto* db = ord::OpenRoad::openRoad()->getDb();
    auto* block = db->getChip()->getBlock();
    auto* tech = db->getTech();
    struct Planned { odb::_dbWire* raw; unsigned index; odb::dbTechVia* via; };
    std::vector<Planned> plans;
    // Validate the entire edit set before modifying the database.
    for (const auto& e : edits) {
      auto* net = block->findNet(e.net);
      auto* via = tech->findVia(e.via);
      if (!net || !net->getWire() || net->getWire()->length() != e.length || !via)
        throw std::runtime_error(std::string("unexpected input: ") + e.net);
      auto* raw = reinterpret_cast<odb::_dbWire*>(net->getWire());
      unsigned count = 0, selected = 0;
      for (unsigned i = 0; i < e.length; ++i) {
        if ((raw->opcodes_[i] & WOP_OPCODE_MASK) != odb::kTechVia
            || raw->data_[i] != static_cast<int>(via->getId())) continue;
        odb::WirePoint point;
        odb::getPrevPoint(tech, block, raw->opcodes_, raw->data_, i - 1, false, point);
        if (point.x == e.x && point.y == e.y) { ++count; selected = i; }
      }
      if (count != 1) throw std::runtime_error(std::string("ambiguous via: ") + e.net);
      unsigned boxes = 0;
      for (auto* box : via->getBoxes()) {
        if (box->getTechLayer()->getName() == e.layer) {
          std::array<int, 4> actual{box->xMin(), box->yMin(), box->xMax(), box->yMax()};
          if (actual != e.before) throw std::runtime_error("unexpected enclosure geometry");
          ++boxes;
        }
      }
      if (boxes != 1) throw std::runtime_error("unexpected enclosure box count");
      const auto name = std::string("T10_V15_MANUAL_") + e.via + "_" + e.layer;
      if (block->findVia(name.c_str())) throw std::runtime_error("patch already applied");
      plans.push_back({raw, selected, via});
    }
    for (unsigned i = 0; i < edits.size(); ++i) {
      const auto& e = edits[i];
      const auto& p = plans[i];
      const auto name = std::string("T10_V15_MANUAL_") + e.via + "_" + e.layer;
      auto* replacement = odb::dbVia::create(block, name.c_str());
      if (!replacement) throw std::runtime_error("cannot create replacement via");
      for (auto* box : p.via->getBoxes()) {
        auto* layer = box->getTechLayer();
        const auto rect = layer->getName() == e.layer ? e.after :
            std::array<int, 4>{box->xMin(), box->yMin(), box->xMax(), box->yMax()};
        odb::dbBox::create(replacement, layer, rect[0], rect[1], rect[2], rect[3]);
      }
      p.raw->opcodes_[p.index] = (p.raw->opcodes_[p.index] & ~WOP_OPCODE_MASK) | odb::kVia;
      p.raw->data_[p.index] = replacement->getId();
    }
    Tcl_SetObjResult(interp, Tcl_NewStringObj("nets=2 vias_replaced=2 coordinates_changed=0", -1));
    return 0;
  } catch (const std::exception& e) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj(e.what(), -1));
    return 1;
  }
}
}

extern "C" int T10manualv15enclosure_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp, "t10_manual_v15_enclosure", patch, nullptr, nullptr);
  return 0;
}
