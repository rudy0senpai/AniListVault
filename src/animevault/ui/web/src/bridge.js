import { useEffect, useState } from "react";

export function useLibrary() {
  const [items, setItems] = useState([]);
  const [bridge, setBridge] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;

    // Load the Qt WebChannel loader script. The QWebChannel class and
    // window.qt.webChannelTransport are set asynchronously by Qt WebEngine
    // after this script executes, so we do NOT short-circuit here. We always
    // attempt to load the script and wire up the channel in onload.
    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onload = () => {
      if (disposed) return;
      if (!window.QWebChannel) {
        setItems([]);
        setReady(true);
        return;
      }
      const transport = window.qt?.webChannelTransport;
      new window.QWebChannel(transport, (channel) => {
        if (disposed) return;
        const api = channel.objects.bridge;
        setBridge(api);
        if (typeof api.getLibrary === "function") {
          api.getLibrary((raw) => {
            if (disposed) return;
            try { setItems(JSON.parse(raw)); } catch { setItems([]); }
            setReady(true);
          });
        } else {
          setItems([]);
          setReady(true);
        }
        if (api.libraryChanged?.connect) {
          api.libraryChanged.connect((raw) => {
            if (disposed) return;
            let event;
            try { event = JSON.parse(raw); } catch { return; }
            if (event.type === "reset") setItems(event.items || []);
            if (event.type === "upsert" && event.item) {
              setItems((current) => current.map((item) => item.id === event.item.id ? event.item : item));
            }
          });
        }
      });
    };
    script.onerror = () => { if (!disposed) setReady(true); };
    document.head.appendChild(script);
    return () => { disposed = true; script.remove(); };
  }, []);

  return { items, bridge, ready };
}
