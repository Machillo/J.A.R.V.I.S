import { useEffect, useMemo, useState } from "react";
import { Brain, Plus, Search, Trash2 } from "lucide-react";
import {
  createMemoryItem,
  deleteMemoryItem,
  getMemorySummary,
  searchMemoryItems,
} from "../services/jarvisApi";
import { deviceLanguage } from "../lib/locale";
const language = deviceLanguage();
const tx = (es, en) => language === "es" ? es : en;

const CATEGORY_LABELS = {
  personal: tx("Datos personales", "Personal data"),
  sports: tx("Deportes", "Sports"),
  voice: tx("Voz", "Voice"),
  style: tx("Estilo", "Style"),
  finance: tx("Finanzas", "Finance"),
  preference: tx("Preferencias", "Preferences"),
  project: tx("Proyecto", "Project"),
  other: tx("General", "General"),
};

export default function Memory() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState({ content: "", category: "preference", importance: 3 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const categories = useMemo(() => Object.entries(CATEGORY_LABELS), []);

  const loadMemory = async () => {
    setLoading(true);
    try {
      const data = await getMemorySummary();
      setSummary(data);
      setItems(data?.items || []);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemory();
  }, []);

  const handleSearch = async () => {
    if (!query.trim()) {
      await loadMemory();
      return;
    }
    setLoading(true);
    try {
      const data = await searchMemoryItems(query.trim());
      setItems(data?.items || []);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.content.trim()) return;
    setSaving(true);
    try {
      await createMemoryItem({
        content: form.content.trim(),
        category: form.category,
        importance: Number(form.importance || 3),
      });
      setForm({ content: "", category: "preference", importance: 3 });
      await loadMemory();
    } catch (error) {
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    await deleteMemoryItem(id);
    setItems((current) => current.filter((item) => item.id !== id));
  };

  return (
    <section className="page memory-page">
      <div className="page-heading-row">
        <div>
          <h1>{tx("Núcleo de memoria", "Memory Core")}</h1>
          <p className="subtitle">{tx("Memoria persistente por usuario. Jarvis usa esto para responder con contexto real.", "Persistent memory per user. Jarvis uses it to respond with real context.")}</p>
        </div>
        <div className="memory-total-pill">
          <Brain size={18} />
          {summary?.total || 0} {tx("recuerdos", "memories")}
        </div>
      </div>

      <div className="memory-grid">
        <div className="jarvis-panel memory-compose-card">
          <h2>{tx("Guardar recuerdo", "Save memory")}</h2>
          <textarea
            value={form.content}
            onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
            placeholder="Ej: Prefiero respuestas cortas. Me interesa F1, UFC y fútbol. Mi tarjeta BAC corta el 21..."
          />

          <div className="memory-form-row">
            <select
              value={form.category}
              onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))}
            >
              {categories.map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
            <select
              value={form.importance}
              onChange={(event) => setForm((current) => ({ ...current, importance: Number(event.target.value) }))}
            >
              <option value={1}>Importancia 1</option>
              <option value={2}>Importancia 2</option>
              <option value={3}>Importancia 3</option>
              <option value={4}>Importancia 4</option>
              <option value={5}>Importancia 5</option>
            </select>
          </div>

          <button className="jarvis-action-button" onClick={handleCreate} disabled={saving || !form.content.trim()}>
            <Plus size={17} />
            {tx("Guardar memoria", "Save memory")}
          </button>
        </div>

        <div className="jarvis-panel memory-profile-card">
          <h2>{tx("Preferencias activas", "Active preferences")}</h2>
          <div className="memory-profile-list">
            {Object.entries(summary?.profile_preferences || {}).map(([key, value]) => (
              <div key={key}>
                <span>{key}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="jarvis-panel memory-list-card">
        <div className="memory-list-header">
          <h2>{tx("Recuerdos guardados", "Saved memories")}</h2>
          <div className="memory-search-box">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleSearch();
              }}
              placeholder={tx("Buscar memoria...", "Search memory...")}
            />
            <button onClick={handleSearch}>{tx("Buscar", "Search")}</button>
          </div>
        </div>

        {loading ? (
          <p className="empty-state">{tx("Cargando memoria...", "Loading memory...")}</p>
        ) : items.length === 0 ? (
          <p className="empty-state">{tx("No hay recuerdos guardados todavía.", "No saved memories yet.")}</p>
        ) : (
          <div className="memory-items">
            {items.map((item) => (
              <article key={item.id} className="memory-item">
                <div>
                  <span className="memory-category">{CATEGORY_LABELS[item.category] || item.category}</span>
                  <p>{item.content}</p>
                  <small>Importancia {item.importance} · {item.source}</small>
                </div>
                <button className="memory-delete" onClick={() => handleDelete(item.id)} aria-label={tx("Eliminar memoria", "Delete memory")}>
                  <Trash2 size={16} />
                </button>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
