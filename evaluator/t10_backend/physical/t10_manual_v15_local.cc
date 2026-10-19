// Hand-designed local fixes for v15 markers 3 and 4; no router search.
#include <array>
#include <exception>
#include <stdexcept>
#include <string>
#include "dbWire.h"
#include "dbWireOpcode.h"
#include "odb/db.h"
#include "odb/dbWireCodec.h"
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
odb::dbVia* reshape(odb::dbBlock* block, odb::dbTech* tech, const char* name,
                    const char* base, const char* edited_layer,
                    std::array<int, 4> before, std::array<int, 4> after) {
  auto* original = tech->findVia(base);
  if (!original || block->findVia(name)) throw std::runtime_error("unexpected via state");
  unsigned matches = 0;
  for (auto* box : original->getBoxes()) {
    if (box->getTechLayer()->getName() == edited_layer) {
      if (std::array<int, 4>{box->xMin(),box->yMin(),box->xMax(),box->yMax()} != before)
        throw std::runtime_error("unexpected original via geometry");
      ++matches;
    }
  }
  if (matches != 1) throw std::runtime_error("unexpected original via boxes");
  auto* via = odb::dbVia::create(block, name);
  for (auto* box : original->getBoxes()) {
    auto* layer = box->getTechLayer();
    auto rect = layer->getName() == edited_layer ? after :
        std::array<int,4>{box->xMin(),box->yMin(),box->xMax(),box->yMax()};
    odb::dbBox::create(via, layer, rect[0],rect[1],rect[2],rect[3]);
  }
  return via;
}

void check_via(odb::_dbWire* raw, unsigned index, odb::dbTechVia* via) {
  if ((raw->opcodes_[index] & WOP_OPCODE_MASK) != odb::kTechVia ||
      raw->data_[index] != static_cast<int>(via->getId()))
    throw std::runtime_error("unexpected wire via operand");
}

void replace_via(odb::_dbWire* raw, unsigned index, odb::dbVia* via) {
  raw->opcodes_[index] = (raw->opcodes_[index] & ~WOP_OPCODE_MASK) | odb::kVia;
  raw->data_[index] = via->getId();
}

void segment(odb::dbWireEncoder& enc, odb::dbTech* tech, const char* layer,
             int x1,int y1,int x2,int y2) {
  enc.newPath(tech->findLayer(layer), odb::dbWireType::ROUTED);
  enc.addPoint(x1,y1); enc.addPoint(x2,y2);
}

void tech_via(odb::dbWireEncoder& enc, odb::dbTech* tech, const char* base,
              const char* lower, int x,int y) {
  enc.newPath(tech->findLayer(lower), odb::dbWireType::ROUTED);
  enc.addPoint(x,y); enc.addTechVia(tech->findVia(base));
}

int patch(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const[]) {
  try {
    if (objc != 1) throw std::runtime_error("usage: t10_manual_v15_local");
    auto* db = ord::OpenRoad::openRoad()->getDb();
    auto* block = db->getChip()->getBlock();
    auto* tech = db->getTech();
    auto* net3 = block->findNet("net22071");
    auto* net4 = block->findNet("quad_sum\\[0\\]\\[355\\]");
    if (!net3 || !net4 || !net3->getWire() || !net4->getWire() ||
        net3->getWire()->length() != 417 || net4->getWire()->length() != 101)
      throw std::runtime_error("unexpected input wire lengths");
    auto* raw3 = reinterpret_cast<odb::_dbWire*>(net3->getWire());
    auto* raw4 = reinterpret_cast<odb::_dbWire*>(net4->getWire());
    check_via(raw3,394,tech->findVia("VIA45"));
    check_via(raw4,99,tech->findVia("VIA56"));
    if ((raw3->opcodes_[184] & WOP_OPCODE_MASK) != odb::kX || raw3->data_[184] != 209916)
      throw std::runtime_error("unexpected M4 endpoint");

    // Marker 3: stack V3/V4 in a 24x46 nm M4 rectangle, and feed it
    // from M2/M3. Both cuts keep their original size and position.
    auto* via45 = reshape(block,tech,"T10_V15_LOCAL_VIA45_M4","VIA45","M4",
                          {-23,-12,23,12},{-12,-23,12,23});
    auto* via34 = reshape(block,tech,"T10_V15_LOCAL_VIA34_M4","VIA34","M4",
                          {-20,-12,20,12},{-12,-23,12,23});
    replace_via(raw3,394,via45);
    raw3->data_[184] = 209808;
    odb::dbWireEncoder enc;
    enc.append(net3->getWire());
    segment(enc,tech,"M3",209808,176292,209808,176364);
    segment(enc,tech,"M2",209808,176292,209916,176292);
    segment(enc,tech,"M3",209916,176292,209916,176364);
    tech_via(enc,tech,"VIA34","M3",209808,176364);
    tech_via(enc,tech,"VIA23","M2",209808,176292);
    tech_via(enc,tech,"VIA23","M2",209916,176292);
    enc.newPath(tech->findLayer("M3"),odb::dbWireType::ROUTED);
    enc.addPoint(209916,176364); enc.addVia(via34);
    // M4 minimum area is 2000 nm^2: a 24x84 nm rectangle has 2016 nm^2.
    enc.newPath(tech->findLayer("M4"),odb::dbWireType::ROUTED);
    enc.addPoint(209916,176364); enc.addRect(-12,-42,12,42);
    enc.end();

    // Marker 4: use the next legal M5 width (120 nm) for the complete
    // 259 nm local rectangle. The V5 EOL enclosure rule applies only
    // to widths <=24.25 nm; the cut and M6 footprint remain unchanged.
    auto* via56 = reshape(block,tech,"T10_V15_LOCAL_VIA56_M5","VIA56","M5",
                          {-12,-27,12,27},{-60,-16,60,16});
    replace_via(raw4,99,via56);
    enc.append(net4->getWire());
    enc.newPath(tech->findLayer("M5"),odb::dbWireType::ROUTED);
    enc.addPoint(133740,414032);
    enc.addRect(-60,-16,60,243);
    enc.end();
    Tcl_SetObjResult(interp,Tcl_NewStringObj("cases=3,4 manual_local_edits_applied",-1));
    return 0;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(error.what(),-1));
    return 1;
  }
}
}
extern "C" int T10manualv15local_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"t10_manual_v15_local",patch,nullptr,nullptr);
  return 0;
}
