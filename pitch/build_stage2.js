// GreenGuardian — Stage-2 review deck. Rebuilds the college template (11 slides, 13.33x7.5,
// Bookman Old Style titles, black on white) with GreenGuardian content.
// Visual language: SOLID black = in the MVP, DASHED outline = planned / not in MVP.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5, same as the template
pres.title = "GreenGuardian - Stage 2 Review";
pres.author = "GreenGuardian team";
pres.theme = { headFontFace: "Bookman Old Style", bodyFontFace: "Times New Roman" };

const BLACK = "000000", INK = "202124", GREY = "595959", MID = "A6A6A6", LIGHT = "F2F2F2", WHITE = "FFFFFF";
const TITLE_FONT = "Bookman Old Style";
const SERIF = "Times New Roman", CAL = "Calibri", ARI = "Arial", MONO = "Courier New";

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: WHITE },
  objects: [
    {
      placeholder: {
        options: { name: "title", type: "title", x: 0.65, y: 0.42, w: 12.0, h: 0.62, fontFace: TITLE_FONT, fontSize: 28, bold: true, color: BLACK, margin: 0, valign: "top", align: "left" },
        text: "",
      },
    },
  ],
});
pres.defineSlideMaster({ title: "TITLE", background: { color: WHITE } });

// ---------- helpers ----------
function box(slide, x, y, w, h, text, o = {}) {
  const planned = !!o.planned;
  slide.addText(text, {
    shape: pres.shapes.RECTANGLE, x, y, w, h, isTextBox: true,
    fill: o.noFill ? undefined : { color: o.fill || (planned ? WHITE : WHITE) },
    line: { color: o.lineColor || (planned ? GREY : BLACK), width: o.lineW || 1, dashType: planned ? "dash" : "solid" },
    fontFace: o.font || CAL, fontSize: o.size || 11, color: o.color || BLACK, bold: !!o.bold, italic: !!o.italic,
    align: o.align || "center", valign: o.valign || "middle", margin: o.margin ?? 4, objectName: o.name,
    paraSpaceAfter: o.paraSpaceAfter,
  });
}
function solid(slide, x, y, w, h, text, o = {}) { box(slide, x, y, w, h, text, { ...o, fill: BLACK, color: WHITE, lineColor: BLACK }); }
function label(slide, text, x, y, w, h, o = {}) {
  slide.addText(text, {
    x, y, w, h, isTextBox: true, fontFace: o.font || CAL, fontSize: o.size || 12, color: o.color || INK, bold: !!o.bold,
    italic: !!o.italic, align: o.align || "left", valign: o.valign || "top", margin: o.margin ?? 0, objectName: o.name,
    paraSpaceAfter: o.paraSpaceAfter,
  });
}
function seg(slide, x1, y1, x2, y2, arrow, color = BLACK, w = 1.25) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color, width: w, endArrowType: arrow ? "triangle" : undefined },
  });
}
// elbow from right-middle of A to left-middle of B through the gap
function elbow(slide, ax, ay, bx, by, midx, color = BLACK) {
  if (Math.abs(ay - by) < 0.01) { seg(slide, ax, ay, bx, by, true, color); return; }
  seg(slide, ax, ay, midx, ay, false, color);
  seg(slide, midx, ay, midx, by, false, color);
  seg(slide, midx, by, bx, by, true, color);
}
function title(slide, text, italic = false) { slide.addText(text, { placeholder: "title", italic }); }
function legend(slide, x, y) {
  box(slide, x, y, 0.32, 0.2, "", { fill: BLACK });
  label(slide, "MVP (being built)", x + 0.4, y - 0.01, 1.6, 0.22, { size: 11, valign: "middle" });
  box(slide, x + 2.05, y, 0.32, 0.2, "", { planned: true });
  label(slide, "Planned (not in MVP)", x + 2.45, y - 0.01, 1.9, 0.22, { size: 11, valign: "middle" });
}

// =====================================================================
// 1. TITLE
// =====================================================================
{
  const s = pres.addSlide({ masterName: "TITLE" });
  s.addImage({ path: path.join(__dirname, "logo.png"), x: 0.67, y: 0.26, w: 2.56, h: 1.81, altText: "New Horizon Institute of Technology and Management logo" });
  const bi = { fontFace: "Bookman Old Style", bold: true, italic: true, color: BLACK, align: "center", isTextBox: true, margin: 0 };
  s.addText("New Horizon Institute of Technology and Management, Thane", { ...bi, x: 3.4, y: 0.62, w: 8.2, h: 0.9, fontSize: 24, valign: "top" });
  s.addText("Department of AI&DS  Engineering", { ...bi, x: 2.2, y: 2.1, w: 10.4, h: 0.5, fontSize: 28 });
  s.addText([
    { text: "GreenGuardian", options: { breakLine: true } },
    { text: "An Operating System for Managing Biological Assets" },
  ], { ...bi, x: 1.7, y: 2.85, w: 11.0, h: 1.2, fontSize: 27, valign: "top" });
  s.addText("By", { ...bi, x: 5.9, y: 4.1, w: 2.4, h: 0.32, fontSize: 20 });
  for (let i = 0; i < 3; i++) {
    s.addText("Student Name- ______________   IEN- ________",
      { ...bi, align: "left", x: 3.4, y: 4.58 + i * 0.4, w: 8.2, h: 0.36, fontSize: 20 });
  }
  s.addText("Guided by: ________________", { ...bi, x: 4.2, y: 6.0, w: 5.6, h: 0.38, fontSize: 20 });
  s.addText("GreenGuardian turns botany from something people observe into something they can manage, predict and optimize.", {
    isTextBox: true, x: 1.4, y: 6.7, w: 10.5, h: 0.4, fontFace: SERIF, fontSize: 15, italic: true, color: GREY, align: "center", margin: 0,
  });
  s.addNotes("Title. GreenGuardian is an operating system for biological assets (trees, plants, crop batches, fields, parks). Student names, IEN numbers and guide must be filled in by the team before submission.");
}

// =====================================================================
// 2. PROBLEM STATEMENT AND OBJECTIVE
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Problem Statement and Objective");
  const L = 0.9, W = 11.6;
  label(s, "Problem Statement", L, 1.3, 5, 0.32, { font: SERIF, size: 18, color: BLACK, bold: true });
  label(s, "Trees, crops and green spaces are tracked in spreadsheets, chat groups and paper registers: state is overwritten, problems are noticed late, and observations rarely become owned, verified action. People can see what exists, but cannot manage what happens next.",
    L, 1.68, W, 0.75, { font: SERIF, size: 15, color: INK });
  label(s, "Objective", L, 2.6, 5, 0.32, { font: SERIF, size: 18, color: BLACK, bold: true });
  label(s, "Build GreenGuardian, one platform that registers biological assets, keeps their state over time, turns observations into structured issues and tasks, and uses a rule-based Botanical Operations Agent to flag what needs attention, for both Green Management and Agricultural Production.",
    L, 2.98, W, 0.75, { font: SERIF, size: 15, color: INK });

  const y = 4.0, h = 2.95, w = 3.75, gap = 0.175, x0 = 0.9;
  // 1. biological asset
  box(s, x0, y, w, h, "", { name: "card-asset" });
  label(s, "What is a biological asset?", x0 + 0.15, y + 0.12, w - 0.3, 0.3, { font: SERIF, size: 15, bold: true, color: BLACK });
  label(s, "A living, managed thing with a lifecycle and a state that changes over time: a tree, a plant, a crop batch (for example 84,200 tomato plants), or the field or zone that holds them.\n\nEvery asset carries a lifecycle stage, observations, issues and tasks.",
    x0 + 0.15, y + 0.5, w - 0.3, h - 0.6, { font: SERIF, size: 13 });
  // 2. who
  const x1 = x0 + w + gap;
  box(s, x1, y, w, h, "", { name: "card-users" });
  label(s, "Who uses it, in two modes", x1 + 0.15, y + 0.12, w - 0.3, 0.3, { font: SERIF, size: 15, bold: true, color: BLACK });
  label(s, [
    { text: "Green Management", options: { bold: true, breakLine: true } },
    { text: "Municipal forestry, parks, campuses, NGOs, afforestation, residential societies.", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    { text: "Agricultural Production", options: { bold: true, breakLine: true } },
    { text: "Farms, orchards, plantations, greenhouses, crop producers.", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    { text: "One platform: the mode changes vocabulary, KPIs and lifecycle, not the data model.", options: { italic: true } },
  ], x1 + 0.15, y + 0.5, w - 0.3, h - 0.6, { font: SERIF, size: 13 });
  // 3. ladder
  const x2 = x1 + w + gap;
  box(s, x2, y, w, h, "", { name: "card-ladder" });
  label(s, "What it manages", x2 + 0.15, y + 0.12, w - 0.3, 0.3, { font: SERIF, size: 15, bold: true, color: BLACK });
  const steps = [
    ["What exists?", false], ["Current state", false], ["What is going wrong?", false],
    ["What will happen?  (V2)", true], ["What should happen next?  (rules now, V3)", true], ["Did the action work?", false],
  ];
  steps.forEach(([t, planned], i) => {
    const yy = y + 0.5 + i * 0.4;
    box(s, x2 + 0.15, yy, w - 0.3, 0.32, t, { planned, fill: planned ? WHITE : BLACK, color: planned ? BLACK : WHITE, font: SERIF, size: 12, name: "ladder-" + i });
  });
  s.addNotes("Problem: assets tracked in spreadsheets and chats; history is lost; observations never become owned action. Objective: an operating system for biological assets. Biological asset = anything living and managed with a lifecycle and time-varying state. Users: Green Management and Agricultural Production share one model. Ladder: solid = delivered by the MVP; dashed = planned (prediction in V2, recommendation in V3). In the MVP 'what should happen next' is rule-based recommendations only.");
}

// =====================================================================
// 3. LITERATURE REVIEW (table, 5 papers)
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Literature Review");
  const H = (t) => ({ text: t, options: { bold: true, fill: { color: LIGHT }, color: BLACK, align: "left", valign: "middle" } });
  const C = (t, o = {}) => ({ text: t, options: { color: INK, valign: "top", ...o } });
  const rows = [
    [H("#"), H("Paper"), H("Method / scope"), H("Reported finding"), H("Gap GreenGuardian addresses")],
    [C("1"), C("Mohanty, Hughes & Salathé (2016). Using deep learning for image-based plant disease detection. Frontiers in Plant Science 7:1419."),
      C("Deep CNN trained on 54,306 leaf images; 14 crop species, 26 diseases (controlled-condition images)."),
      C("99.35% accuracy on a held-out test set."),
      C("A classifier, not a system: no asset history, issue or task. Our planned Disease Detection feeds Observation → Issue → Task.")],
    [C("2"), C("Kamilaris & Prenafeta-Boldú (2018). Deep learning in agriculture: a survey. Computers and Electronics in Agriculture 147:70-90."),
      C("Survey of 40 studies applying deep learning to agricultural problems."),
      C("Deep learning gives high accuracy and outperforms common image-processing techniques."),
      C("Focus is per-task model accuracy; the operating loop (issue → task → verify) is outside its scope.")],
    [C("3"), C("Wolfert, Ge, Verdouw & Bogaardt (2017). Big data in smart farming: a review. Agricultural Systems 153:69-80."),
      C("Literature review of big-data applications in smart farming (IoT, cloud, analytics)."),
      C("Big data provides predictive insight and real-time operational decisions across the food chain."),
      C("Farm and supply-chain focus; we apply the same data-to-decision loop to farms and urban green assets on one model.")],
    [C("4"), C("van Klompenburg, Kassahun & Catal (2020). Crop yield prediction using machine learning: a systematic literature review. Computers and Electronics in Agriculture 177:105709."),
      C("Systematic review: 567 studies retrieved, 50 analysed."),
      C("CNN, LSTM and DNN are the most-used deep-learning algorithms for yield prediction."),
      C("Prediction needs history. The MVP records time-stamped data now, so yield prediction has real training data later.")],
    [C("5"), C("Hilbert, Roman, Koeser, Vogt & van Doorn (2019). Urban tree mortality: a literature review. Arboriculture & Urban Forestry 45(5):167-200."),
      C("Review of urban tree mortality rates and risk factors (56 studies)."),
      C("Tree survival is a performance metric; knowing mortality factors helps managers target resources."),
      C("Motivates our Green Management KPIs (survival, health) and per-tree records that make survival measurable.")],
  ];
  s.addTable(rows, {
    x: 0.65, y: 1.3, w: 12.05, colW: [0.4, 3.55, 2.75, 2.65, 2.7],
    fontFace: SERIF, fontSize: 11, border: { type: "solid", pt: 0.75, color: MID }, margin: [0.05, 0.07, 0.05, 0.07],
    rowH: [0.34, 0.95, 0.85, 0.95, 1.0, 0.95],
  });
  label(s, "Observed gap (our reading of these five papers): strong models for single tasks (detect, predict) and strong evidence that survival and health matter, but little on one system that registers assets, tracks their state over time, turns findings into owned tasks and checks the outcome.",
    0.65, 6.55, 12.05, 0.6, { font: SERIF, size: 13, italic: true, color: BLACK });
  s.addNotes("Five peer-reviewed sources, each verified against its published record. Papers 1, 2, 4 show what intelligence models can do; paper 3 shows data-driven farm decision-making; paper 5 shows why urban tree survival needs per-tree records. The gap is the operating loop around the models. The gap statement is our reading, not a claim made by the papers.");
}

// =====================================================================
// 4. SCOPE
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Scope");
  const lx = 0.65, lw = 6.55, rx = 7.45, rw = 5.25, top = 1.25;
  solid(s, lx, top, lw, 0.4, "MVP: the operational foundation, being built now", { font: SERIF, size: 14, bold: true });
  box(s, rx, top, rw, 0.4, "Planned: designed for, not in the MVP", { planned: true, font: SERIF, size: 14, bold: true });
  const mvp = [
    ["Assets", "Trees · plants · crops · batches · fields · zones · species"],
    ["Monitoring", "Health · growth · observations · photos · lifecycle stage"],
    ["Operations", "Tasks · inspections · treatments · irrigation · planting · harvest records"],
    ["Botanical Issues", "Create · severity · assignment · workflow · resolution · history"],
    ["Map", "Assets, health, issues and tasks layers"],
    ["Dashboards", "Green: survival, health, growth, canopy, coverage. Agri: growth, health, yield, harvest, revenue (yield, harvest and revenue estimates stay 'Coming soon')"],
    ["Botanical Operations Agent", "Rules, thresholds, statistical anomaly checks, weather context → structured recommendations"],
  ];
  const hs = [0.58, 0.58, 0.58, 0.58, 0.5, 0.9, 0.72];
  let yy = top + 0.5;
  mvp.forEach(([k, v], i) => {
    box(s, lx, yy, 1.75, hs[i], k, { fill: LIGHT, font: SERIF, size: 12, bold: true, align: "left", margin: 6 });
    box(s, lx + 1.75, yy, lw - 1.75, hs[i], v, { font: SERIF, size: 12, align: "left", margin: 6 });
    yy += hs[i] + 0.06;
  });
  const fut = [
    ["V2 · Prediction", "Disease detection (image → computer vision → issue → task) · growth, survival, yield and harvest prediction", 1.5],
    ["V3 · Recommendation", "Crop recommendation (soil + weather + location + water + season + market) · irrigation recommendation · profitability range", 1.5],
    ["V4 · Optimization", "Best operating strategy under land, water, labour, weather, crop economics and risk constraints", 1.2],
  ];
  yy = top + 0.5;
  fut.forEach(([k, v, h]) => {
    box(s, rx, yy, rw, h, "", { planned: true });
    label(s, k, rx + 0.12, yy + 0.08, rw - 0.24, 0.28, { font: SERIF, size: 13, bold: true, color: BLACK });
    label(s, v, rx + 0.12, yy + 0.4, rw - 0.24, h - 0.45, { font: SERIF, size: 12 });
    yy += h + 0.1;
  });
  label(s, "Planned modules already appear in the MVP interface as 'Coming soon' with real layouts. No predicted or recommended value is shown until a real model produces it.",
    rx, yy + 0.02, rw, 0.9, { font: SERIF, size: 12, italic: true, color: BLACK });
  label(s, "Each stage needs real recorded data, so the MVP captures time-stamped observations, treatments, costs and outcomes from day one.",
    lx, 6.75, lw, 0.45, { font: SERIF, size: 12, italic: true, color: GREY });
  s.addNotes("Scope. Solid = MVP, dashed = planned. MVP = asset registry, monitoring, operations, Botanical Issues, map, dashboards, rules-based Botanical Operations Agent. Evolution: MVP operational foundation -> V2 prediction -> V3 recommendation -> V4 optimization. Future modules are visible in the UI as Coming soon; nothing fabricated. Out of scope for MVP: any ML or LLM model, PDF reports, notifications, SSO, offline sync.");
}

// =====================================================================
// 5. WORKFLOW OF PROJECT  (swimlane: activities, responsibilities, data exchanged)
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Workflow of Project", true);
  const lanesY = 1.2, laneH = 0.98, labelW = 1.45, x0 = 0.65;
  const laneNames = ["Field worker", "Botanical Operations Agent (system)", "Manager / owner"];
  laneNames.forEach((n, i) => {
    box(s, x0, lanesY + i * laneH, labelW, laneH - 0.06, n, { fill: LIGHT, font: CAL, size: 11, bold: true, margin: 4 });
    box(s, x0 + labelW + 0.05, lanesY + i * laneH, 12.05 - labelW - 0.05, laneH - 0.06, "", { lineColor: MID, lineW: 0.75, name: "lane-" + i });
  });
  const colX = (c) => 2.3 + c * 1.7, bw = 1.5, bh = 0.74;
  const by = (lane) => lanesY + lane * laneH + 0.07;
  const steps = [
    { c: 0, lane: 0, t: "1 Register asset\n(species, place, stage)" },
    { c: 1, lane: 0, t: "2 Record observation\n(health, symptoms, photo)" },
    { c: 2, lane: 1, t: "3 Evaluate rules\n→ recommendation + why" },
    { c: 3, lane: 2, t: "4 Accept → botanical issue + task" },
    { c: 4, lane: 0, t: "5 Field action,\nlog the result" },
    { c: 5, lane: 0, t: "6 Recheck:\nnew observation" },
    { c: 5, lane: 2, t: "7 Resolve issue\nafter verification" },
  ];
  steps.forEach((st, i) => solid(s, colX(st.c), by(st.lane), bw, bh, st.t, { size: 11, name: "wf-" + i }));
  const mid = (st) => by(st.lane) + bh / 2;
  const right = (st) => colX(st.c) + bw;
  const link = (a, b) => elbow(s, right(steps[a]), mid(steps[a]), colX(steps[b].c), mid(steps[b]), right(steps[a]) + 0.1);
  link(0, 1); link(1, 2); link(2, 3); link(3, 4); link(4, 5);
  // recheck (lane 0, col 5) -> resolve (lane 2, col 5): vertical arrow in the same column
  seg(s, colX(5) + bw / 2, by(0) + bh, colX(5) + bw / 2, by(2), true);
  // data exchanged
  const data = ["asset record", "observation + photo", "recommendation + evidence", "issue + task + assignee", "task result + notes", "health record + history"];
  label(s, "Data exchanged", x0, lanesY + 3 * laneH + 0.02, labelW, 0.3, { size: 11, bold: true, italic: true, font: CAL });
  data.forEach((d, c) => label(s, d, colX(c), lanesY + 3 * laneH + 0.02, bw, 0.4, { size: 10.5, italic: true, align: "center", color: GREY, font: CAL }));

  // mode journeys
  const jy = 4.85;
  label(s, "Same loop, two modes: asset → lifecycle → issue → task → outcome", x0, jy - 0.05, 8, 0.3, { size: 13, bold: true, font: CAL, color: BLACK });
  legend(s, 8.35, jy);
  const chips = (y, name, items) => {
    box(s, x0, y, 1.2, 0.62, name, { fill: LIGHT, font: CAL, size: 11, bold: true });
    const n = items.length, gap = 0.09, w = (12.05 - 1.2 - 0.1 - gap * (n - 1)) / n;
    items.forEach(([t, planned], i) => {
      const x = x0 + 1.3 + i * (w + gap);
      if (planned) box(s, x, y, w, 0.62, t, { planned: true, font: CAL, size: 10 });
      else solid(s, x, y, w, 0.62, t, { font: CAL, size: 10 });
    });
  };
  chips(jy + 0.4, "Agricultural production", [
    ["Create farm", 0], ["Define fields", 0], ["Create batch", 0], ["Monitor health", 0], ["Observe", 0], ["Issue → task", 0], ["Field action", 0], ["Recheck", 0], ["Harvest", 0],
    ["Predict growth, yield, harvest", 1], ["Revenue and profit range", 1],
  ]);
  chips(jy + 1.12, "Green management", [
    ["Create green space", 0], ["Define zones", 0], ["Register trees", 0], ["Map", 0], ["Inspect", 0], ["Issue → task", 0], ["Intervene", 0], ["Monitor survival", 0],
    ["Canopy and coverage (if measured)", 1], ["Impact report", 0],
  ]);
  label(s, "Crop selection is manual in the MVP; crop recommendation is planned (V3).", x0 + 1.3, jy + 1.8, 10.5, 0.25, { size: 11, italic: true, color: GREY, font: CAL });
  s.addNotes("Workflow as a swimlane showing activities, who is responsible, and the data exchanged. 1 Worker registers asset. 2 Worker records observation. 3 Agent evaluates rules and writes a recommendation with the reason. 4 Manager accepts: a botanical issue and a task are created and assigned. 5 Worker acts and logs result. 6 Worker rechecks. 7 Manager resolves after verification. Below: the same loop for Agricultural Production and Green Management; dashed steps are planned.");
}

// =====================================================================
// 6. SYSTEM ARCHITECTURE & DESIGN DIAGRAMS
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "System Architecture & Design Diagrams");
  // left: block diagram
  label(s, "Block diagram", 0.65, 1.15, 5, 0.28, { size: 14, bold: true, font: CAL, color: BLACK });
  const lx = 0.65, lw = 5.9;
  solid(s, lx, 1.5, lw, 0.55, "Browser / PWA: React + TypeScript (mode-aware UI, map, dashboards)", { font: CAL, size: 11.5 });
  seg(s, lx + lw / 2, 2.05, lx + lw / 2, 2.4, true);
  label(s, "HTTPS · REST/JSON · /api/v1", lx + lw / 2 + 0.1, 2.12, 2.6, 0.25, { size: 10, italic: true, color: GREY, font: CAL });
  solid(s, lx, 2.4, lw, 0.65, "API: FastAPI · auth + roles · workspace scoping · services (issues, tasks, observations)", { font: CAL, size: 11.5 });
  const bw3 = 1.85, g3 = 0.175;
  [["Worker\nagent runs · jobs", 0], ["PostgreSQL + PostGIS\nassets · history · state", 1], ["Object storage\nphotos · reports", 2]].forEach(([t, i]) => {
    seg(s, lx + i * (bw3 + g3) + bw3 / 2, 3.05, lx + i * (bw3 + g3) + bw3 / 2, 3.4, true);
    solid(s, lx + i * (bw3 + g3), 3.4, bw3, 0.75, t, { font: CAL, size: 11 });
  });
  label(s, "Providers and models", lx, 4.3, 5, 0.25, { size: 11, bold: true, font: CAL });
  box(s, lx, 4.58, bw3, 0.62, "Weather provider", { font: CAL, size: 11 });
  box(s, lx + bw3 + g3, 4.58, bw3, 0.62, "ML / CV inference (V2)", { planned: true, font: CAL, size: 11 });
  box(s, lx + 2 * (bw3 + g3), 4.58, bw3, 0.62, "LLM layer (later)", { planned: true, font: CAL, size: 11 });
  label(s, "Modular monolith: one codebase, two processes (API, worker). Rules run in the worker and only write recommendations; a person accepts them.",
    lx, 5.35, lw, 0.65, { size: 11.5, italic: true, color: INK, font: CAL });

  // right: biological asset graph (ERD)
  label(s, "Biological asset graph (core entities)", 7.0, 1.15, 5.7, 0.28, { size: 14, bold: true, font: CAL, color: BLACK });
  const cx = [7.0, 8.95, 10.9], cw = 1.8, nh = 0.62, ry = [1.5, 2.55, 3.6, 4.65, 5.7];
  const node = (c, r, t, planned = false) => planned ? box(s, cx[c], ry[r], cw, nh, t, { planned: true, font: CAL, size: 11 }) : solid(s, cx[c], ry[r], cw, nh, t, { font: CAL, size: 11 });
  node(0, 0, "Workspace\n(mode)"); node(1, 0, "Project"); node(2, 0, "Location\n(field · zone)");
  node(1, 1, "Species / crop\ncatalog"); node(2, 1, "Biological asset\n(tree · plant · batch)");
  node(0, 2, "Photos\n(attachments)"); node(1, 2, "Health + growth\nrecords"); node(2, 2, "Observation\n(append-only)");
  node(1, 3, "Recommendation\n(rules agent)"); node(2, 3, "Botanical issue\n(+ status history)");
  node(1, 4, "Treatment · harvest\nrecords"); node(2, 4, "Task\n(+ status history)");
  node(0, 4, "Prediction\n(reserved, V2)", true);
  const hmid = (r) => ry[r] + nh / 2;
  seg(s, cx[0] + cw, hmid(0), cx[1], hmid(0), true);
  seg(s, cx[1] + cw, hmid(0), cx[2], hmid(0), true);
  seg(s, cx[2] + cw / 2, ry[0] + nh, cx[2] + cw / 2, ry[1], true);
  seg(s, cx[1] + cw, hmid(1), cx[2], hmid(1), false); // species -> asset (reverse arrow below)
  seg(s, cx[2], hmid(1), cx[1] + cw, hmid(1), true);
  seg(s, cx[2] + cw / 2, ry[1] + nh, cx[2] + cw / 2, ry[2], true);
  seg(s, cx[2], hmid(2), cx[1] + cw, hmid(2), true);
  seg(s, cx[1], hmid(2), cx[0] + cw, hmid(2), true);
  seg(s, cx[2] + cw / 2, ry[2] + nh, cx[2] + cw / 2, ry[3], true);
  seg(s, cx[1] + cw, hmid(3), cx[2], hmid(3), true);
  seg(s, cx[2] + cw / 2, ry[3] + nh, cx[2] + cw / 2, ry[4], true);
  seg(s, cx[2], hmid(4), cx[1] + cw, hmid(4), true);
  label(s, "evidence", cx[2] + cw / 2 + 0.08, ry[2] + nh + 0.08, 0.9, 0.22, { size: 10, italic: true, color: GREY, font: CAL });
  label(s, "tasks", cx[2] + cw / 2 + 0.08, ry[3] + nh + 0.08, 0.9, 0.22, { size: 10, italic: true, color: GREY, font: CAL });

  // bottom: three layers
  const ly = 6.5, lw3 = 3.95, lg = 0.1;
  [["ASSET layer: what exists", "assets · locations · species"], ["OPERATIONS layer: what needs to happen", "issues · tasks · inspections · harvests"], ["INTELLIGENCE layer: what next", "rules now; models later"]].forEach(([a, b], i) => {
    const x = 0.65 + i * (lw3 + lg);
    box(s, x, ly, lw3, 0.62, "", { fill: LIGHT, lineColor: MID, lineW: 0.75 });
    label(s, a, x + 0.1, ly + 0.05, lw3 - 0.2, 0.26, { size: 11.5, bold: true, font: CAL, color: BLACK });
    label(s, b, x + 0.1, ly + 0.32, lw3 - 0.2, 0.26, { size: 11, font: CAL });
  });
  s.addNotes("Left: block diagram. Browser to FastAPI API to PostgreSQL/PostGIS, object storage and a worker for rules. Weather provider is part of the MVP; ML inference and LLM are planned (dashed). Right: the biological asset graph. Asset -> observation (append-only) -> issue -> task, with the agent producing recommendations that a person accepts. State is never overwritten; history tables are append-only. Bottom: three product layers: asset, operations, intelligence. Because both modes use this one graph, the same platform supports trees and agriculture.");
}

// =====================================================================
// 7. METHODOLOGY & ALGORITHM WORKFLOW
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Methodology & Algorithm Workflow");
  label(s, "Botanical Operations Agent: rules, not ML", 0.65, 1.12, 5, 0.28, { size: 14, bold: true, font: ARI, color: BLACK });
  const px = 0.65, pw = 3.4;
  const pipe = ["Inputs: asset state, observation history, weather", "Evaluate rules (thresholds per workspace)", "De-duplicate by rule + subject", "Recommendation with explanation", "Person accepts → issue or task"];
  pipe.forEach((t, i) => {
    const y = 1.5 + i * 0.78;
    (i === 4 ? box : solid)(s, px, y, pw, 0.55, t, { font: ARI, size: 11 });
    if (i < 4) seg(s, px + pw / 2, y + 0.55, px + pw / 2, y + 0.78, true);
  });
  // rules table
  const H = (t) => ({ text: t, options: { bold: true, fill: { color: LIGHT }, color: BLACK, valign: "middle" } });
  const C = (t, o = {}) => ({ text: t, options: { color: INK, valign: "middle", ...o } });
  const rows = [
    [H("Rule"), H("Trigger"), H("Output"), H("Status")],
    [C("Inspection gap"), C("now − last_observed_at > 21 days"), C("Inspection task"), C("MVP")],
    [C("Health decline"), C("score(oldest) − score(newest) ≥ 15 pts within 14 days, ≥ 2 observations"), C("Issue"), C("MVP (statistical)")],
    [C("Symptom cluster"), C("≥ 5 assets in one zone share a symptom"), C("Cluster issue"), C("MVP")],
    [C("Irrigation deferral"), C("rain forecast ≥ R mm and soil moisture ≥ M"), C("Irrigation advice"), C("MVP, needs weather + soil data")],
    [C("Harvest window"), C("batch reaches its configured stage duration"), C("Harvest task"), C("MVP (stage rule, not a forecast)")],
    [C("Canopy decline"), C("zone canopy falls > X% in 90 days"), C("Inspection task"), C("Needs canopy measurements")],
  ];
  s.addTable(rows, {
    x: 4.35, y: 1.5, w: 8.35, colW: [1.55, 3.55, 1.35, 1.9], fontFace: ARI, fontSize: 10.5,
    border: { type: "solid", pt: 0.75, color: MID }, margin: [0.04, 0.06, 0.04, 0.06], rowH: [0.32, 0.5, 0.62, 0.42, 0.62, 0.62, 0.5],
  });
  // issue workflows
  const iy = 5.45;
  label(s, "Observation → Botanical issue: each transition is validated and written to history", 0.65, iy - 0.05, 9, 0.28, { size: 13, bold: true, font: ARI, color: BLACK });
  const flow = (y, id, stages) => {
    label(s, id, 0.65, y, 3.0, 0.5, { size: 10.5, bold: true, font: ARI, valign: "middle" });
    const w = 1.62, g = 0.22;
    stages.forEach((t, i) => {
      const x = 3.7 + i * (w + g);
      box(s, x, y + 0.05, w, 0.42, t, { font: ARI, size: 10.5, fill: i === 0 ? BLACK : WHITE, color: i === 0 ? WHITE : BLACK });
      if (i < stages.length - 1) seg(s, x + w, y + 0.26, x + w + g, y + 0.26, true);
    });
  };
  flow(iy + 0.3, "GG-001 Neem Tree: leaf yellowing", ["OPEN", "INVESTIGATING", "TREATMENT", "MONITORING", "RESOLVED"]);
  flow(iy + 0.85, "GG-002 Tomato field: possible fungal infection", ["OPEN", "FIELD INSPECTION", "TREATMENT", "MONITORING", "RESOLVED"]);
  label(s, "Health band: Healthy ≥ 70 · At risk 40-69 · Critical < 40 (configurable). Output is labelled RULE or STATISTICAL; MODEL and LLM labels appear only when a real model exists.",
    0.65, 7.05, 12.05, 0.3, { size: 10.5, italic: true, color: GREY, font: ARI });
  s.addNotes("Methodology. The agent is a set of explainable rules over structured data: a pipeline from inputs to rules to de-duplication to a recommendation that a person accepts. Algorithms are simple and stated: gap = now - last observation; decline = oldest score - newest score inside a window; cluster = count of assets per (zone, symptom). Rules for irrigation, harvest window and canopy need extra data (weather, soil moisture, stage duration, canopy measurements) and are labelled as such. The harvest rule is a stage-duration rule, not a prediction. Issue workflows GG-001 and GG-002 show how observations become structured issues.");
}

// =====================================================================
// 8. FEASIBILITY & TECHNOLOGY STACK
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Feasibility & Technology Stack");
  const H = (t) => ({ text: t, options: { bold: true, fill: { color: LIGHT }, color: BLACK, valign: "middle" } });
  const C = (t, o = {}) => ({ text: t, options: { color: INK, valign: "middle", ...o } });
  const rows = [
    [H("Layer"), H("Choice"), H("Why")],
    [C("Frontend", { bold: true }), C("React, TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, MapLibre GL, Recharts"), C("Open-source, mature, typed")],
    [C("Backend", { bold: true }), C("Python, FastAPI, Pydantic, SQLAlchemy, Alembic"), C("Typed API; same language as later ML")],
    [C("Database", { bold: true }), C("PostgreSQL 16 + PostGIS"), C("Spatial queries, constraints, history")],
    [C("Jobs", { bold: true }), C("DB-backed job table + APScheduler"), C("No extra service in the MVP")],
    [C("Storage", { bold: true }), C("S3-compatible (MinIO for local)"), C("Photos and reports")],
    [C("Intelligence", { bold: true }), C("Rules and statistics now; scikit-learn, PyTorch, OpenCV or an LLM API only when a real model exists"), C("No ML dependency in the MVP")],
    [C("Delivery", { bold: true }), C("Docker, GitHub Actions, OpenAPI /api/v1"), C("Repeatable builds and tests")],
  ];
  s.addTable(rows, {
    x: 0.65, y: 1.3, w: 7.9, colW: [1.3, 4.4, 2.2], fontFace: CAL, fontSize: 12,
    border: { type: "solid", pt: 0.75, color: MID }, margin: [0.05, 0.08, 0.05, 0.08], rowH: [0.34, 0.72, 0.6, 0.6, 0.6, 0.55, 0.9, 0.6],
  });
  const fx = 8.85, fw = 3.85;
  box(s, fx, 1.3, fw, 4.75, "", { fill: WHITE });
  label(s, "Feasibility", fx + 0.15, 1.4, fw - 0.3, 0.3, { size: 14, bold: true, font: CAL, color: BLACK });
  label(s, [
    { text: "Hardware: ", options: { bold: true } }, { text: "no special hardware. Development laptops, and a phone camera for field photos.", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    { text: "Software: ", options: { bold: true } }, { text: "open-source stack; hosted on container or free-tier services (to be confirmed).", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    { text: "Data: ", options: { bold: true } }, { text: "weather from a public API (Open-Meteo assumed, to be confirmed); observations come from users.", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    { text: "Main risks", options: { bold: true, breakLine: true } },
    { text: "PostGIS setup on dev machines (no Docker yet): use docker-compose or a hosted dev database.", options: { bullet: true, breakLine: true } },
    { text: "Scope creep: MVP and planned features are kept strictly apart.", options: { bullet: true, breakLine: true } },
    { text: "Over-claiming AI: outputs are labelled rule, statistical, model or LLM.", options: { bullet: true } },
  ], fx + 0.15, 1.78, fw - 0.3, 4.2, { size: 12, font: CAL, paraSpaceAfter: 2 });
  s.addNotes("Stack chosen for typed end-to-end development, spatial support and a clean path to ML later. No ML framework is a dependency of the MVP. Open items to confirm: hosting target and weather provider.");
}

// =====================================================================
// 9. WORK DISTRIBUTION & TIMELINE (GANTT)
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Work Distribution & Timeline (Gantt Chart)");
  const roles = [
    ["Member 1: ____________", "Product and frontend", "React UI, map, dashboards, future-feature surfaces, presentation"],
    ["Member 2: ____________", "Engine and backend", "API, database and migrations, rules engine, jobs"],
    ["Member 3: ____________", "Integration and quality", "CI, deployment, tests, documentation, demo data"],
  ];
  const rw = 3.9, rg = 0.175;
  roles.forEach(([n, r, d], i) => {
    const x = 0.65 + i * (rw + rg);
    box(s, x, 1.2, rw, 1.2, "", { fill: LIGHT, lineColor: MID, lineW: 0.75 });
    label(s, n, x + 0.12, 1.26, rw - 0.24, 0.26, { size: 12, bold: true, font: CAL, color: BLACK });
    label(s, r, x + 0.12, 1.54, rw - 0.24, 0.26, { size: 12, bold: true, font: CAL });
    label(s, d, x + 0.12, 1.82, rw - 0.24, 0.55, { size: 11.5, font: CAL });
  });
  // gantt
  const gx = 4.05, gy = 2.65, cw = 0.72, labW = gx - 0.65, rh = 0.4, weeks = 12;
  box(s, 0.65, gy, labW, 0.3, "Work package", { fill: LIGHT, font: CAL, size: 11, bold: true, align: "left", margin: 6 });
  box(s, gx, gy, 6 * cw, 0.3, "Stage 3 (assumed W1-W6)", { fill: LIGHT, font: CAL, size: 11, bold: true });
  box(s, gx + 6 * cw, gy, 6 * cw, 0.3, "Stage 4 (assumed W7-W12)", { fill: LIGHT, font: CAL, size: 11, bold: true });
  for (let w = 0; w < weeks; w++) box(s, gx + w * cw, gy + 0.3, cw, 0.26, "W" + (w + 1), { font: CAL, size: 10, lineColor: MID, lineW: 0.5 });
  const tasks = [
    ["Scaffold, CI, database baseline", 1, 2],
    ["Identity, workspaces, roles, tenant tests", 2, 3],
    ["Assets, locations, lifecycle", 3, 4],
    ["Observations, health and growth, state", 4, 5],
    ["Issues and tasks workflow", 5, 7],
    ["Botanical Operations Agent (rules)", 6, 8],
    ["Map and dashboards (both modes)", 7, 9],
    ["Reports, future-feature surfaces, polish", 9, 11],
    ["Hardening, end-to-end tests, deployment", 11, 12],
  ];
  const top = gy + 0.56;
  tasks.forEach(([t, a, b], i) => {
    const y = top + i * rh;
    box(s, 0.65, y, labW, rh, t, { font: CAL, size: 11, align: "left", margin: 6, lineColor: MID, lineW: 0.5 });
    for (let w = 0; w < weeks; w++) box(s, gx + w * cw, y, cw, rh, "", { lineColor: MID, lineW: 0.5 });
    solid(s, gx + (a - 1) * cw + 0.04, y + 0.08, (b - a + 1) * cw - 0.08, rh - 0.16, "", {});
  });
  label(s, "Done so far: product documentation and PRD, architecture and schema design, rules-engine proof of concept. Weeks are relative to this review; map them to the Stage 3 and 4 calendar. Member names to be filled in.",
    0.65, top + tasks.length * rh + 0.12, 12.05, 0.5, { size: 11.5, italic: true, color: GREY, font: CAL });
  s.addNotes("Roles are split by lane. Names must be filled in by the team. The Gantt chart uses relative weeks because the Stage 3 and Stage 4 calendar dates are not in the template; the split at week 6 is an assumption to adjust. Order follows the build plan: scaffold, identity, assets, observations, issues and tasks, agent, map and dashboards, reports and polish, hardening.");
}

// =====================================================================
// 10. INITIAL / PARTIAL IMPLEMENTATION (PoC)
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Initial/Partial Implementation (Proof of Concept)");
  const out = fs.readFileSync(path.join(__dirname, "_work", "poc_output.txt"), "utf8").replace(/\r/g, "").trimEnd().split("\n");
  label(s, "Rules engine: real run on sample data", 0.65, 1.15, 6.5, 0.28, { size: 14, bold: true, font: CAL, color: BLACK });
  const termLines = ["$ python poc_run.py", ...out, "", "$ python -m pytest -q", "5 passed in 0.02s"];
  s.addText(termLines.join("\n"), {
    shape: pres.shapes.RECTANGLE, isTextBox: true, x: 0.65, y: 1.5, w: 6.7, h: 3.55,
    fill: { color: "1E1E1E" }, line: { color: BLACK, width: 1 }, fontFace: MONO, fontSize: 10, color: "E6E6E6",
    align: "left", valign: "top", margin: 10, objectName: "terminal",
  });
  label(s, "Tests cover boundary cases, time window, clustering and de-duplication. Input is synthetic sample data, not real observations.",
    0.65, 5.12, 6.7, 0.5, { size: 11.5, italic: true, color: GREY, font: CAL });

  // wireframe
  label(s, "Mock UI screen (design wireframe, not running software)", 7.65, 1.15, 5.1, 0.28, { size: 14, bold: true, font: CAL, color: BLACK });
  const wx = 7.65, wy = 1.5, ww = 5.05, wh = 4.1;
  box(s, wx, wy, ww, wh, "", { lineColor: BLACK, lineW: 1.25 });
  box(s, wx, wy, 1.5, wh, "", { fill: LIGHT, lineColor: BLACK, lineW: 1.25 });
  const nav = [["ASSETS", 0], ["WORK", 0], ["MONITOR", 0], ["AI", 0]];
  const navItems = [
    ["Assets", 0], ["Tasks · Issues", 0], ["Map", 0], ["Agent", 0], ["Crop Recommendation", 1], ["Disease Detection", 1], ["Yield Prediction", 1],
  ];
  label(s, "WORKSPACE\nCity Green Cover", wx + 0.1, wy + 0.08, 1.35, 0.4, { size: 9.5, bold: true, font: CAL, color: BLACK });
  navItems.forEach(([t, soon], i) => {
    label(s, t, wx + 0.1, wy + 0.62 + i * 0.4, 1.35, soon ? 0.36 : 0.22, { size: 9.5, font: CAL, color: soon ? GREY : BLACK, italic: !!soon });
    if (soon) label(s, "Coming soon", wx + 0.1, wy + 0.62 + i * 0.4 + 0.17, 1.3, 0.16, { size: 8, font: CAL, color: GREY });
  });
  const mx = wx + 1.65, mw = ww - 1.8;
  label(s, "Home: attention inbox", mx, wy + 0.1, mw, 0.25, { size: 11, bold: true, font: CAL, color: BLACK });
  const tiles = ["Trees", "Healthy", "At risk", "Critical"];
  tiles.forEach((t, i) => box(s, mx + i * (mw / 4), wy + 0.42, mw / 4 - 0.06, 0.55, t + "\n(live count)", { font: CAL, size: 9 }));
  box(s, mx, wy + 1.07, mw / 2 - 0.04, 0.5, "Canopy: not enough data", { planned: true, font: CAL, size: 9 });
  box(s, mx + mw / 2 + 0.02, wy + 1.07, mw / 2 - 0.04, 0.5, "Survival forecast: Coming soon", { planned: true, font: CAL, size: 9 });
  [["Tree #482 not observed in 23 days", "Create task"], ["6 plants in Zone B show leaf_spot", "Create issue"], ["Neem #101 health fell 24 pts", "Create issue"]].forEach(([t, b], i) => {
    const y = wy + 1.72 + i * 0.7;
    box(s, mx, y, mw, 0.62, "", { lineColor: MID, lineW: 0.75 });
    label(s, t, mx + 0.08, y + 0.05, mw - 0.16, 0.24, { size: 10, bold: true, font: CAL, color: BLACK });
    label(s, "Rule · why?", mx + 0.08, y + 0.33, 1.0, 0.2, { size: 9, font: CAL, color: GREY });
    solid(s, mx + mw - 1.05, y + 0.31, 0.95, 0.24, b, { font: CAL, size: 9 });
  });
  label(s, "Wireframe values are illustrative. Planned modules show 'Coming soon' with no fabricated output.", wx, wy + wh + 0.06, ww, 0.4, { size: 10.5, italic: true, color: GREY, font: CAL });

  // status strip
  box(s, 0.65, 6.2, 12.05, 0.85, "", { fill: LIGHT, lineColor: MID, lineW: 0.75 });
  label(s, [
    { text: "Done: ", options: { bold: true } }, { text: "PRD and documentation set, architecture, database schema, API specification, rules-engine proof of concept with tests.", options: { breakLine: true } },
    { text: "Next: ", options: { bold: true } }, { text: "scaffold FastAPI and React, PostGIS database, authentication and workspace isolation, then assets and observations.", options: {} },
  ], 0.8, 6.27, 11.75, 0.7, { size: 12, font: CAL });
  s.addNotes("Proof of concept: the Botanical Operations Agent rules engine runs on synthetic sample data and its 5 unit tests pass; the three outputs match the example recommendations in the product story. The UI is a wireframe of the planned home screen, clearly labelled as a mock. Dashed items show how planned modules appear as Coming soon. The application backend and frontend are not built yet; next steps are listed at the bottom.");
}

// =====================================================================
// 11. INDUSTRY APPROVAL LETTER
// =====================================================================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  title(s, "Industry Approval Letter (On Company letterhead)");
  box(s, 1.2, 1.5, 10.9, 5.2, "Insert the signed industry approval letter here (scan or photo on company letterhead)", {
    planned: true, font: SERIF, size: 18, italic: true, color: GREY,
  });
  s.addNotes("Placeholder: the signed approval letter on company letterhead must be supplied by the team and the industry contact; it cannot be generated.");
}

// Never overwrite GreenGuardian-Stage2-Review.pptx: it is hand-edited in PowerPoint (names, IEN, letter images).
// The generator writes a separate file; copy slides across deliberately if you want its content.
pres.writeFile({ fileName: path.join(__dirname, "GreenGuardian-Stage2-Review.generated.pptx") }).then((f) => console.log("wrote", f));
