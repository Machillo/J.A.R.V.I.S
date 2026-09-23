import { useEffect, useMemo, useState } from "react";
import { Brain, Plus, Search, Trash2 } from "lucide-react";
import {
  createMemoryItem,
  deleteMemoryItem,
  getMemorySummary,
  searchMemoryItems,
} from "../services/jarvisApi";
import { deviceLanguage } from "../lib/locale";
import { JarvisGlassCard, JarvisScreen, JarvisStatusPill } from "../products/jarvis/components/JarvisScreen";
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
    <JarvisScreen eyebrow={tx("Memoria", "Memory")} title={tx("Núcleo de memoria", "Memory core")} subtitle={tx("Contexto personal utilizado por DINCR", "Personal context used by DINCR")} className="memory-screen">
      <JarvisGlassCard className="memory-status-card">
        <Brain size={29} />
        <div><strong>{summary?.total || 0} {tx("recuerdos", "memories")}</strong><small>{Object.keys(summary?.profile_preferences || {}).length} {tx("preferencias activas · sincronizado", "active preferences · synced")}</small></div>
        <JarvisStatusPill tone="success">{tx("ACTIVA", "ACTIVE")}</JarvisStatusPill>
      </JarvisGlassCard>

      <JarvisGlassCard className="memory-compose-card">
          <h3>{tx("Guardar un recuerdo", "Save a memory")}</h3>
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

          <button className="jarvis-primary-button memory-save-button" type="button" onClick={handleCreate} disabled={saving || !form.content.trim()}>
            <Plus size={17} />
            {tx("Guardar", "Save")}
          </button>
      </JarvisGlassCard>

      <div className="memory-section">
          <h3>{tx("Preferencias activas", "Active preferences")}</h3>
          <div className="memory-profile-list">
            {Object.entries(summary?.profile_preferences || {}).map(([key, value]) => (
              <JarvisGlassCard as="div" key={key}>
                <span>{key}</span>
                <strong>{String(value)}</strong>
              </JarvisGlassCard>
            ))}
          </div>
      </div>

      <div className="memory-section memory-list-card">
        <div className="memory-list-header">
          <h3>{tx("Recuerdos recientes", "Recent memories")}</h3>
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
            <button type="button" onClick={handleSearch} aria-label={tx("Buscar", "Search")}><Search size={14} /></button>
          </div>
        </div>

        {loading ? (
          <p className="empty-state">{tx("Cargando memoria...", "Loading memory...")}</p>
        ) : items.length === 0 ? (
          <p className="empty-state">{tx("No hay recuerdos guardados todavía.", "No saved memories yet.")}</p>
        ) : (
          <div className="memory-items">
            {items.map((item) => (
              <JarvisGlassCard key={item.id} className="memory-item">
                <div>
                  <span className="memory-category">{CATEGORY_LABELS[item.category] || item.category}</span>
                  <p>{item.content}</p>
                </div>
                <button className="memory-delete" onClick={() => handleDelete(item.id)} aria-label={tx("Eliminar memoria", "Delete memory")}>
                  <Trash2 size={16} />
                </button>
              </JarvisGlassCard>
            ))}
          </div>
        )}
      </div>
    </JarvisScreen>
  );
}
