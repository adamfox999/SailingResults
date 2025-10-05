"use client";

import type { ChangeEvent, FormEvent } from "react";
import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { API_BASE, fetcher } from "../../api-client";
import { formatDisplayDate, toDateInputValue } from "../../utils/datetime";
import type { Series, SeriesListResponse } from "../../types";
import styles from "./page.module.css";

interface CreateFormState {
  title: string;
  code: string;
  startDate: string;
  endDate: string;
}

interface EditFormState {
  title: string;
  startDate: string;
  endDate: string;
}

const SERIES_KEY = "/series";

const createInitialFormState = (): CreateFormState => ({
  title: "",
  code: "",
  startDate: "",
  endDate: "",
});

export default function SeriesAdminPage() {
  const [form, setForm] = useState<CreateFormState>(() => createInitialFormState());
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditFormState>({ title: "", startDate: "", endDate: "" });
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const { mutate } = useSWRConfig();
  const { data, error, isLoading } = useSWR<SeriesListResponse>(SERIES_KEY, fetcher);
  const series = useMemo(() => data?.series ?? [], [data]);

  const sortedSeries = useMemo(() => {
    const clone = [...series];
    clone.sort((a, b) => {
      const dateA = a.startDate ? new Date(a.startDate).valueOf() : Number.MAX_SAFE_INTEGER;
      const dateB = b.startDate ? new Date(b.startDate).valueOf() : Number.MAX_SAFE_INTEGER;
      if (dateA === dateB) {
        return a.title.localeCompare(b.title);
      }
      return dateA - dateB;
    });
    return clone;
  }, [series]);

  const handleCreateChange = (key: keyof CreateFormState) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [key]: event.target.value }));
      setFormError(null);
      setFormSuccess(null);
    };

  const handleEditChange = (key: keyof EditFormState) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setEditForm((current) => ({ ...current, [key]: event.target.value }));
      setEditError(null);
      setEditSuccess(null);
    };

  const resetEditState = () => {
    setEditingId(null);
    setEditForm({ title: "", startDate: "", endDate: "" });
    setEditError(null);
    setEditSuccess(null);
    setIsSavingEdit(false);
  };

  const handleCreateSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    if (!form.title.trim()) {
      setFormError("Series title is required.");
      return;
    }

    const payload = {
      title: form.title.trim(),
      code: form.code.trim() || undefined,
      startDate: form.startDate ? form.startDate : undefined,
      endDate: form.endDate ? form.endDate : undefined,
    };

    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/series`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail?.detail as string) ?? "Failed to create series");
      }

      const created = (await response.json()) as Series;
      await mutate(SERIES_KEY);
      setFormSuccess(`Added series ${created.title} (${created.code}).`);
      setForm(createInitialFormState());
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unexpected error while creating series.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (record: Series) => {
    setEditingId(record.id);
    setEditForm({
      title: record.title,
      startDate: record.startDate ? toDateInputValue(record.startDate) : "",
      endDate: record.endDate ? toDateInputValue(record.endDate) : "",
    });
    setEditError(null);
    setEditSuccess(null);
  };

  const handleEditSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingId) return;

    setEditError(null);
    setEditSuccess(null);

    const trimmedTitle = editForm.title.trim();
    if (!trimmedTitle) {
      setEditError("Series title is required.");
      return;
    }

    const payload: Record<string, unknown> = {
      title: trimmedTitle,
    };

    if (editForm.startDate) {
      payload.startDate = editForm.startDate;
    } else {
      payload.startDate = null;
    }

    if (editForm.endDate) {
      payload.endDate = editForm.endDate;
    } else {
      payload.endDate = null;
    }

    setIsSavingEdit(true);
    try {
      const response = await fetch(`${API_BASE}/series/${editingId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail?.detail as string) ?? "Failed to update series");
      }

      const updated = (await response.json()) as Series;
      await mutate(SERIES_KEY);
      setEditSuccess(`Saved ${updated.title}.`);
      setTimeout(() => {
        resetEditState();
      }, 1500);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Unexpected error while updating series.");
      setIsSavingEdit(false);
    }
  };

  return (
    <main className={styles.container}>
      <section className={styles.card}>
        <h2>Add a series</h2>
        <form onSubmit={handleCreateSubmit} className={styles.form}>
          <div className={styles.formGrid}>
            <label>
              Title
              <input value={form.title} onChange={handleCreateChange("title")} placeholder="e.g. Autumn Series" />
            </label>
            <label>
              Code
              <input
                value={form.code}
                onChange={handleCreateChange("code")}
                placeholder="Optional – leave blank to auto-generate"
              />
            </label>
            <label>
              Start date
              <input type="date" value={form.startDate} onChange={handleCreateChange("startDate")} />
            </label>
            <label>
              End date
              <input type="date" value={form.endDate} onChange={handleCreateChange("endDate")} />
            </label>
          </div>
          <div className={styles.formActions}>
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Save series"}
            </button>
          </div>
          {formError && <p className={styles.error}>{formError}</p>}
          {formSuccess && <p className={styles.success}>{formSuccess}</p>}
        </form>
      </section>

      <section className={styles.card}>
        <div className={styles.sectionHeader}>
          <h2>Existing series</h2>
          <span className={styles.countBadge}>{sortedSeries.length}</span>
        </div>
        {error && <p className={styles.error}>Failed to load series: {error.message}</p>}
        {isLoading && <p>Loading series…</p>}
        {!isLoading && !error && sortedSeries.length === 0 && <p className={styles.muted}>No series found yet.</p>}
        {!isLoading && !error && sortedSeries.length > 0 && (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Start date</th>
                  <th>End date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedSeries.map((item) => {
                  const isEditing = editingId === item.id;
                  return (
                    <tr key={item.id}>
                      <td>{item.code}</td>
                      <td>
                        {isEditing ? (
                          <input
                            value={editForm.title}
                            onChange={handleEditChange("title")}
                            className={styles.inlineInput}
                          />
                        ) : (
                          item.title
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="date"
                            value={editForm.startDate}
                            onChange={handleEditChange("startDate")}
                            className={styles.inlineInput}
                          />
                        ) : (
                          item.startDate ? formatDisplayDate(item.startDate) : ""
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="date"
                            value={editForm.endDate}
                            onChange={handleEditChange("endDate")}
                            className={styles.inlineInput}
                          />
                        ) : (
                          item.endDate ? formatDisplayDate(item.endDate) : ""
                        )}
                      </td>
                      <td className={styles.actionsCell}>
                        {isEditing ? (
                          <form onSubmit={handleEditSubmit} className={styles.inlineForm}>
                            <button type="submit" disabled={isSavingEdit}>
                              {isSavingEdit ? "Saving…" : "Save"}
                            </button>
                            <button type="button" className={styles.ghostButton} onClick={resetEditState}>
                              Cancel
                            </button>
                          </form>
                        ) : (
                          <button type="button" className={styles.ghostButton} onClick={() => startEdit(item)}>
                            Edit
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {editError && <p className={styles.error}>{editError}</p>}
        {editSuccess && <p className={styles.success}>{editSuccess}</p>}
      </section>
    </main>
  );
}
