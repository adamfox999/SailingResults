"use client";

import type { ChangeEvent, FormEvent } from "react";
import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { clsx } from "clsx";
import { API_BASE, fetcher } from "../../api-client";
import { formatDisplayDate, toDateInputValue, toTimeInputValue } from "../../utils/datetime";
import type { ScheduledRace, ScheduledRacesResponse, Series, SeriesListResponse } from "../../types";
import styles from "./page.module.css";

interface FormState {
  seriesId: string;
  raceNumber: string;
  date: string;
  startTime: string;
  raceOfficer: string;
  notes: string;
}

const createInitialFormState = (): FormState => {
  const todayIso = new Date().toISOString();
  return {
    seriesId: "",
    raceNumber: "",
    date: toDateInputValue(todayIso),
    startTime: "",
    raceOfficer: "",
    notes: "",
  };
};

const SCHEDULED_RACES_KEY = "/scheduled-races?includePast=true";
const SERIES_KEY = "/series";

const computeStatus = (race: ScheduledRace, nowValue: number): "past" | "upcoming" => {
  const reference = race.startTime ? new Date(race.startTime) : new Date(`${race.date}T23:59:59`);
  return reference.valueOf() < nowValue ? "past" : "upcoming";
};

export default function AdminRacesPage() {
  const [form, setForm] = useState<FormState>(() => createInitialFormState());
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { mutate } = useSWRConfig();

  const { data, error, isLoading } = useSWR<ScheduledRacesResponse>(SCHEDULED_RACES_KEY, fetcher);
  const {
    data: seriesData,
    error: seriesError,
    isLoading: isSeriesLoading,
  } = useSWR<SeriesListResponse>(SERIES_KEY, fetcher);
  const races = useMemo(() => data?.races ?? [], [data]);
  const seriesOptions = useMemo<Series[]>(() => seriesData?.series ?? [], [seriesData]);
  const nowValue = Date.now();

  const sortedRaces = useMemo(() => {
    const clone = [...races];
    clone.sort((a, b) => {
      const timeA = new Date(a.startTime || `${a.date}T00:00:00`).valueOf();
      const timeB = new Date(b.startTime || `${b.date}T00:00:00`).valueOf();
      return timeA - timeB;
    });
    return clone;
  }, [races]);

  const handleChange = (key: keyof FormState) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((current) => ({ ...current, [key]: event.target.value }));
      setFormError(null);
      setSuccessMessage(null);
    };

  const handleSeriesChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setForm((current) => ({ ...current, seriesId: event.target.value }));
    setFormError(null);
    setSuccessMessage(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    const selectedSeries = seriesOptions.find((item) => item.id === form.seriesId);
    if (!selectedSeries) {
      setFormError("Please choose a series before scheduling a race.");
      return;
    }

    const raceNumberValue = form.raceNumber.trim();
    const parsedRaceNumber = raceNumberValue ? Number.parseInt(raceNumberValue, 10) : null;
    if (parsedRaceNumber !== null && Number.isNaN(parsedRaceNumber)) {
      setFormError("Race number must be a whole number.");
      return;
    }

    const raceLabel = parsedRaceNumber !== null ? `Race ${parsedRaceNumber}` : selectedSeries.title || selectedSeries.code;
    const seriesName = selectedSeries.title || selectedSeries.code;

    const payload = {
      series: seriesName,
      race: raceLabel,
      raceNumber: parsedRaceNumber,
      date: form.date,
      startTime: form.startTime ? form.startTime : null,
      raceOfficer: form.raceOfficer.trim() || null,
      notes: form.notes.trim() || null,
    };

    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/scheduled-races`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail?.detail as string) ?? "Failed to create scheduled race");
      }
      const created = (await response.json()) as ScheduledRace;
      await Promise.all([
        mutate("/scheduled-races"),
        mutate(SCHEDULED_RACES_KEY),
      ]);
      setSuccessMessage(
        `Scheduled ${created.series} ${created.race}${created.raceNumber ? ` (#${created.raceNumber})` : ""} on ${formatDisplayDate(
          created.date,
        )}.`,
      );
      setForm(() => ({
        ...createInitialFormState(),
        seriesId: selectedSeries.id,
        raceOfficer: payload.raceOfficer ?? "",
      }));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unexpected error while scheduling race.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.container}>
      <header className={styles.header}>
        <h2>Scheduled races</h2>
        <p className={styles.tagline}>Create the season plan and keep race metadata ready for the duty officer.</p>
      </header>

      <section className={styles.card}>
        <h2>Plan a new race</h2>
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.formGrid}>
            <label>
              Series
              <select
                value={form.seriesId}
                onChange={handleSeriesChange}
                disabled={isSeriesLoading || Boolean(seriesError)}
              >
                <option value="">Select a series…</option>
                {seriesOptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} {item.code ? `(${item.code})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Race number
              <input
                value={form.raceNumber}
                onChange={handleChange("raceNumber")}
                type="number"
                min="1"
                placeholder="e.g. 5"
              />
            </label>
            <label>
              Date
              <input type="date" value={form.date} onChange={handleChange("date")} />
            </label>
            <label>
              Start time
              <input type="time" value={form.startTime} onChange={handleChange("startTime")} />
            </label>
            <label>
              Race officer
              <input
                value={form.raceOfficer}
                onChange={handleChange("raceOfficer")}
                placeholder="Optional"
              />
            </label>
          </div>
          {seriesError && <p className={styles.error}>Failed to load series: {seriesError.message}</p>}
          <label className={styles.notesField}>
            Notes
            <textarea
              value={form.notes}
              onChange={handleChange("notes")}
              rows={3}
              placeholder="Logistics, start sequence, safety notes…"
            />
          </label>
          <div className={styles.formActions}>
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Save race"}
            </button>
          </div>
          {formError && <p className={styles.error}>{formError}</p>}
          {successMessage && <p className={styles.success}>{successMessage}</p>}
        </form>
      </section>

      <section className={styles.card}>
        <div className={styles.sectionHeader}>
          <h2>Race calendar</h2>
          <span className={styles.countBadge}>{sortedRaces.length}</span>
        </div>
        {error && <p className={styles.error}>Failed to load scheduled races: {error.message}</p>}
        {isLoading && <p>Loading race calendar…</p>}
        {!isLoading && !error && sortedRaces.length === 0 && <p className={styles.muted}>No races scheduled yet.</p>}
        {!isLoading && !error && sortedRaces.length > 0 && (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Series</th>
                  <th>Race</th>
                  <th>Start</th>
                  <th>Officer</th>
                  <th>Notes</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {sortedRaces.map((race) => {
                  const status = computeStatus(race, nowValue);
                  const startLabel = toTimeInputValue(race.startTime);
                  return (
                    <tr key={race.id}>
                      <td>{formatDisplayDate(race.date)}</td>
                      <td>{race.series}</td>
                      <td>
                        {race.race}
                        {race.raceNumber != null && (
                          <span className={styles.subtleMeta}>#{race.raceNumber}</span>
                        )}
                      </td>
                      <td>{startLabel}</td>
                      <td>{race.raceOfficer ?? ""}</td>
                      <td className={styles.notesCell}>{race.notes ?? ""}</td>
                      <td>
                        <span className={clsx(styles.statusChip, status === "past" ? styles.past : styles.upcoming)}>
                          {status === "past" ? "Past" : "Upcoming"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
