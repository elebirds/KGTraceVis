# Wafer Sources

Record source excerpts or private-source summaries used for wafer KG construction here.
Do not commit confidential raw data.

## Coverage-First Candidate KG Sources

- `wm811k_public_pattern_classes`: WM811K public defect-pattern vocabulary used
  by the local producer/model path: Center, Donut, Edge-Loc, Edge-Ring, Loc,
  Random, Scratch, and Near-full. These classes are defect-pattern evidence, not
  process root-cause labels.
- `wm811k_pattern_semantics`: deterministic class-to-location/morphology rules
  aligned with the wafer-map descriptor helper in `src/kgtracevis/mask/`.
- `wm811k_low_confidence_investigation_rule`: conservative candidate mechanism
  mappings used to generate plausible investigation paths. These default to
  `review_status=auto` and low/medium confidence unless separately reviewed.
- `wafer_thesis`: base wafer development reference for a plausible nearfull
  investigation mechanism. This is not a verified factory root-cause label
  unless separately reviewed against private incident evidence.
- `wafer_factory_sop_private_summary`: private wet-clean SOP summary used only
  for low-confidence WM811K investigation targets. Short evidence snippets are
  copied into generated edge evidence; raw private files are not committed.
- `wafer_wet_bench_manual_private_summary`: private wet-bench and WTS manuals
  summarized only for equipment, alarm, process-unit, and transfer vocabulary.
- `wafer_wet_bench_component_naming_private_summary`: private naming workbook
  summarized only for component/HMI/program aliases.
- `wafer_machine_log_private_summary`: private machine-log collection
  summarized only for observed event/alarm vocabulary after decoding and case
  alignment.
- `wafer_recipe_private_summary`: private recipe-file collection summarized
  only for recipe-step and parameter vocabulary; not used as RCA evidence
  without paired defect labels.

## Private Source Audit

Private files were reviewed only to create safe source summaries. Do not copy
raw private documents into the repository or generated paper artifacts.

| Private file | Usefulness | Safe KG use | Short evidence snippets |
| --- | --- | --- | --- |
| `异常SOP.txt` | High | Wet-clean SOP summary for low-confidence WM811K investigation mechanisms. | `未开启纯水会导致nearfull缺陷`; `未开启兆声水会导致nearfull缺陷`; `水阻率异常导致晶圆near full缺陷`; `去胶不充分导致边缘环缺陷`; `掉片导致晶圆划痕缺陷` |
| `EN-05-D77-150 8寸WTS 设备通讯手册.pdf` | Medium | Equipment communication, alarm, and log-event vocabulary; not defect RCA. | Use summarized alarm/event names only. |
| `EN-05-D77-151 8寸 WTS 设备手册.pdf` | Medium | Equipment module and operation vocabulary for entity aliases; not defect RCA. | Use summarized equipment terms only. |
| `湿法设备零部件&电气元件&程序&HMI&上位软件命名规范 V2024-01.xlsx` | Medium-low | Component, HMI, and program aliases for entity linking. | Naming aliases only; no RCA claims. |
| `1599#陪片 说明书-最终版.docx` | Low | Recipe or carrier/context vocabulary only unless paired with defect labels. | No defect-RCA snippets used. |
| `本1.pdf` | Low/no | OCR-heavy or unreadable PDF source; avoid direct KG claims. | No snippets used. |
| `本1_1-200.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `本1_201-400.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `本1_401-576.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `本2.pdf` | Low/no | OCR-heavy or unreadable PDF source; avoid direct KG claims. | No snippets used. |
| `本2.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `本3.pdf` | Low/no | OCR-heavy or unreadable PDF source; avoid direct KG claims. | No snippets used. |
| `本3.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `本4.pdf` | Low/no | OCR-heavy or unreadable PDF source; avoid direct KG claims. | No snippets used. |
| `本4.docx` | Medium | Equipment/manual vocabulary extracted from readable converted pages. | No defect-RCA snippets used. |
| `机台日志/` | Medium | Operator/run-state logs can support event and alarm vocabulary after decoding and case alignment. | Use summarized alarm/event names only; no defect-RCA snippets used. |
| `设备配方/RecipeFile` | Low | Recipe-step and parameter vocabulary only unless paired with defect evidence. | Use summarized modes/parameters only; no RCA claims. |

Machine logs and recipe files are present but are not currently used to create
RCA edges. They may become observed evidence sources after schema parsing and
case alignment; until then, use them only for event, alarm, recipe, and
parameter vocabulary.
