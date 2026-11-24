import { useCallback, useEffect, useState } from "react";
import { BubbleButton, BubbleMenu, BubbleTabs } from "./LiquidGlass.jsx";
import "./topbar.css";

const CATEGORIES = [
  { id: "anime", label: "Anime" },
  { id: "manga", label: "Manga" },
  { id: "manhwa", label: "Manhwa" },
  { id: "manhua", label: "Manhua" },
];
const RECOMMENDATIONS_ITEMS = [
  { label: "Open Recommendations", action: "recommendations" },
  { label: "Refresh All Data", action: "refresh_all" },
  { divider: true },
  { label: "Settings", action: "settings" },
];
const DELETE_ITEMS = [
  { label: "Delete Selected", action: "delete_selected" },
];
const SELECT_ITEMS = [
  { label: "Toggle Selection Mode", action: "toggle_selection_mode" },
];
const FETCH_ITEMS = [
  { label: "Fetch Missing Data", action: "fetch_missing" },
  { label: "Refresh All Data", action: "refresh_all" },
];
const RETRY_ITEMS = [
  { label: "Retry Failed", action: "retry_failed" },
];
const TOOLS_ITEMS = [
  { label: "Library Dashboard", action: "dashboard" },
  { label: "Fetch Missing Data", action: "fetch_missing" },
  { label: "Refresh Anime Data", action: "refresh_all" },
  { divider: true },
  { label: "Cloud Sync…", action: "cloud_sync" },
];
const HELP_ITEMS = [
  { label: "About AnimeVault", action: "about" },
  { label: "README", action: "open_readme" },
];
const UPLOAD_ITEMS = [
  { label: "Import Excel (.xlsx)…", action: "import_xlsx" },
  { label: "Import CSV (.csv)…", action: "import_csv" },
  { label: "Import SQL Dump (.sql)…", action: "import_sql" },
];
const EXPORT_ITEMS = [
  { label: "Export to CSV…", action: "export_csv" },
  { label: "Export to Excel (.xlsx)…", action: "export_xlsx" },
  { label: "Export to OpenDocument (.ods)…", action: "export_ods" },
  { label: "Export to SQL Dump…", action: "export_sql" },
];

export default function TopBar({ bridge, surface = "all" }) {
  const [category, setCategory] = useState("anime");
  const [selectedCount, setSelectedCount] = useState(0);
  const [selectionMode, setSelectionMode] = useState(false);
  const [retryAvailable, setRetryAvailable] = useState(false);
  const invoke = useCallback((action) => bridge?.menuAction(action), [bridge]);

  useEffect(() => {
    if (!bridge) return;
    bridge.getCategory(setCategory);
    bridge.getSelectedCount(setSelectedCount);
    bridge.getRetryAvailable(setRetryAvailable);
    const selected = (count) => setSelectedCount(count);
    const retry = (available) => setRetryAvailable(available);
    const mode = (enabled) => setSelectionMode(enabled);
    const changedCategory = (value) => setCategory(value);
    bridge.selectionChanged.connect(selected);
    bridge.retryAvailableChanged.connect(retry);
    bridge.selectionModeChanged.connect(mode);
    bridge.categoryChanged.connect(changedCategory);
    return () => {
      bridge.selectionChanged.disconnect(selected);
      bridge.retryAvailableChanged.disconnect(retry);
      bridge.selectionModeChanged.disconnect(mode);
      bridge.categoryChanged.disconnect(changedCategory);
    };
  }, [bridge]);

  const menuItems = (items) => items.map((item) => item.divider
    ? item
    : item.action
      ? ({ label: item.label, danger: item.danger, onSelect: () => invoke(item.action) })
      : ({ label: item.label }));
  const selectCategory = (value) => invoke(`category:${value}`);
  const toggleSelection = () => bridge?.setSelectionMode(!selectionMode);
  const onMenuToggle = (open, itemCount) => bridge?.setMenuOpen(open, itemCount);

  return <div className={`av-liquid-topbar av-liquid-topbar--${surface}`}>
    {surface !== "toolbar" && <div className="av-liquid-brand-row">
      <div className="av-liquid-brand"><span aria-hidden="true">◐</span><strong>AnimeVault</strong></div>
      <BubbleTabs tabs={CATEGORIES} value={category} onChange={selectCategory} />
      <span className="av-liquid-spacer" />
      <BubbleButton aria-label="Settings" title="Settings" onClick={() => invoke("settings")}>⚙</BubbleButton>
    </div>}
    {surface !== "nav" && <div className="av-liquid-actions">
      <BubbleMenu label="Tools" items={menuItems(TOOLS_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="🎯 Recommendations" items={menuItems(RECOMMENDATIONS_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="Help" items={menuItems(HELP_ITEMS)} onOpenChange={onMenuToggle} />
      <span className="av-liquid-gap" />
      <BubbleMenu label="⇧ Upload" items={menuItems(UPLOAD_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="⤓ Export" items={menuItems(EXPORT_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="▤ Delete" items={menuItems(DELETE_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label={selectionMode ? "✓ Selecting" : "✓ Select"} items={menuItems(SELECT_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="⟳ Fetch Missing Data" items={menuItems(FETCH_ITEMS)} onOpenChange={onMenuToggle} />
      <BubbleMenu label="↻ Retry Failed" items={menuItems(RETRY_ITEMS)} onOpenChange={onMenuToggle} />
    </div>}
  </div>;
}
