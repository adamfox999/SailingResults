"use client";

import Link from "next/link";
import type { ChangeEvent } from "react";
import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { API_BASE, fetcher } from "./api-client";
import { formatDisplayDate, toDateInputValue, toTimeInputValue } from "./utils/datetime";
import type { ScheduledRace, ScheduledRacesResponse } from "./types";
import styles from "./page.module.css";

interface ClassOption {
  key: string;
  label: string;
}

interface ReferenceData {
  classes: Record<string, number>;
  classOptions: ClassOption[];
  finCodes: string[];
}

interface ProfileBoat {
  className: string;
  sailNumber?: string | null;
}

interface ProfileRosterEntry {
  id: string;
  helm: string;
  crew?: string | null;
  boats: ProfileBoat[];
}

interface ProfileRosterResponse {
  profiles: ProfileRosterEntry[];
}

type NormalisedProfileBoat = {
  classKey: string | null;
  label: string;
  sailNumber: string;
};

interface EntryRow {
  id: string;
  entryId?: string;
  helm: string;
  crew: string;
  sailNumber: string;
  dinghy: string;
  personal: string;
  laps: string;
  timeSeconds: string;
  finCode: string;
}

interface MetadataState {
  series: string;
  race: string;
  raceNumber: string;
  startTime: string;
  date: string;
  raceOfficer: string;
}

interface PyResult {
  entryId: string;
  helm: string;
  crew: string;
  dinghy: string;
  py: number;
  laps: number;
  timeSeconds: number;
  corrected: number | null;
  rank: number | null;
  finCode: string;
}

interface PersonalResult {
  entryId: string;
  helm: string;
  crew: string;
  personalHandicap: number;
  corrected: number | null;
  rank: number | null;
}

interface ScoreResponse {
  metadata: {
    series: string;
    race: string;
    raceNumber?: number | null;
    raceOfficer: string;
    date: string;
    startTime?: string | null;
    filename: string;
    generatedAt: string;
  };
  pyResults: PyResult[];
  personalResults: PersonalResult[];
  summary: string;
  html: string;
}

const createId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2, 10);
};

const blankRow = (): EntryRow => ({
  id: createId(),
  helm: "",
  crew: "",
  sailNumber: "",
  dinghy: "",
  personal: "0",
  laps: "",
  timeSeconds: "",
  finCode: "",
});

const PEOPLE_DATALIST_ID = "entry-people-options";

const initialMetadata = (): MetadataState => {
  const today = new Date();
  const dd = String(today.getDate()).padStart(2, "0");
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const yyyy = today.getFullYear();
  return {
    series: "",
    race: "",
    raceNumber: "",
    startTime: "",
    raceOfficer: "",
    date: `${yyyy}-${mm}-${dd}`,
  };
};

export default function HomePage() {
  const [metadata, setMetadata] = useState<MetadataState>(initialMetadata);
  const [rows, setRows] = useState<EntryRow[]>(() => Array.from({ length: 10 }, blankRow));
  const [results, setResults] = useState<ScoreResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isScoring, setIsScoring] = useState(false);
  const [selectedScheduleId, setSelectedScheduleId] = useState<string>("");

  const { data: reference, error: referenceError, isLoading: referenceLoading } = useSWR<ReferenceData>(
    "/reference",
    fetcher,
  );

  const {
    data: scheduled,
    error: scheduleError,
    isLoading: scheduleLoading,
  } = useSWR<ScheduledRacesResponse>("/scheduled-races", fetcher);

  const {
    data: rosterData,
    error: rosterError,
    isLoading: rosterLoading,
  } = useSWR<ProfileRosterResponse>("/profiles-roster", fetcher);

  const rosterProfiles = useMemo(() => rosterData?.profiles ?? [], [rosterData]);

  const scheduledRaces = useMemo(() => scheduled?.races ?? [], [scheduled]);

  const finCodes = useMemo(() => reference?.finCodes ?? ["", "DNF", "DNC", "OCS", "RET", "DSQ"], [
    reference,
  ]);

  const classOptions = useMemo(() => reference?.classOptions ?? [], [reference]);

  const classLookupMaps = useMemo(() => {
    const byKey = new Map<string, ClassOption>();
    const byLabel = new Map<string, ClassOption>();

    classOptions.forEach((option) => {
      const key = option.key.trim().toUpperCase();
      const label = option.label.trim().toUpperCase();
      byKey.set(key, option);
      byLabel.set(label, option);
    });

    return { byKey, byLabel };
  }, [classOptions]);

  const rosterNameOptions = useMemo(() => {
    const seen = new Set<string>();
    const names: string[] = [];

    const addName = (name: string | null | undefined) => {
      const trimmed = (name ?? "").trim();
      if (!trimmed) {
        return;
      }
      const key = trimmed.toLowerCase();
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      names.push(trimmed);
    };

    rosterProfiles.forEach((profile) => {
      addName(profile.helm);
      addName(profile.crew);
    });

    names.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return names;
  }, [rosterProfiles]);

  const rosterNameBoatMap = useMemo(() => {
    const { byKey, byLabel } = classLookupMaps;

    const normaliseBoats = (boats: ProfileBoat[] | undefined | null): NormalisedProfileBoat[] => {
      if (!boats?.length) {
        return [];
      }
      const seen = new Set<string>();
      const list: NormalisedProfileBoat[] = [];
      for (const boat of boats) {
        const className = (boat.className ?? "").trim();
        if (!className) {
          continue;
        }
        const sailNumber = (boat.sailNumber ?? "").trim();
        const canonical = className.toUpperCase();
        const option = byKey.get(canonical) ?? byLabel.get(canonical);
        const classKey = (option?.key ?? canonical).toUpperCase();
        const label = option?.label ?? className;
        const dedupeKey = `${classKey}|${sailNumber}`;
        if (seen.has(dedupeKey)) {
          continue;
        }
        seen.add(dedupeKey);
        list.push({ classKey, label, sailNumber });
      }
      return list;
    };

    const addBoatsForName = (targetName: string | null | undefined, boats: NormalisedProfileBoat[]) => {
      const trimmed = (targetName ?? "").trim();
      if (!trimmed || boats.length === 0) {
        return;
      }
      const key = trimmed.toLowerCase();
      const existing = rosterMap.get(key) ? [...(rosterMap.get(key) as NormalisedProfileBoat[])] : [];
      const seenKeys = new Set(existing.map((boat) => `${boat.classKey}|${boat.sailNumber}`));
      boats.forEach((boat) => {
        const dedupeKey = `${boat.classKey}|${boat.sailNumber}`;
        if (seenKeys.has(dedupeKey)) {
          return;
        }
        seenKeys.add(dedupeKey);
        existing.push(boat);
      });
      rosterMap.set(key, existing);
    };

    const rosterMap = new Map<string, NormalisedProfileBoat[]>();

    rosterProfiles.forEach((profile) => {
      const boats = normaliseBoats(profile.boats);
      addBoatsForName(profile.helm, boats);
      addBoatsForName(profile.crew, boats);
    });

    return rosterMap;
  }, [classLookupMaps, rosterProfiles]);

  const getBoatsForNames = useCallback(
    (helmName: string, crewName: string): NormalisedProfileBoat[] => {
      const combined: NormalisedProfileBoat[] = [];
      const seen = new Set<string>();

      const pushFromName = (name: string) => {
        const key = name.trim().toLowerCase();
        if (!key) {
          return;
        }
        const list = rosterNameBoatMap.get(key);
        if (!list) {
          return;
        }
        list.forEach((boat) => {
          const dedupeKey = `${boat.classKey}|${boat.sailNumber}`;
          if (seen.has(dedupeKey)) {
            return;
          }
          seen.add(dedupeKey);
          combined.push({ ...boat });
        });
      };

      pushFromName(helmName ?? "");
      pushFromName(crewName ?? "");

      return combined;
    },
    [rosterNameBoatMap],
  );

  const getBoatLookupForNames = useCallback(
    (helmName: string, crewName: string) => {
      const lookup = new Map<string, NormalisedProfileBoat>();
      getBoatsForNames(helmName, crewName).forEach((boat) => {
        if (!boat.classKey) {
          return;
        }
        const key = boat.classKey.toUpperCase();
        if (!lookup.has(key)) {
          lookup.set(key, boat);
        }
      });
      return lookup;
    },
    [getBoatsForNames],
  );

  const getClassDropdownOptions = useCallback(
    (helmName: string, crewName: string) => {
      const boats = getBoatsForNames(helmName, crewName);
      if (!boats.length) {
        return {
          preferred: [] as ClassOption[],
          remaining: classOptions,
        };
      }

      const preferredKeys = new Set<string>();
      const preferred: ClassOption[] = [];

      boats.forEach((boat) => {
        if (!boat.classKey) {
          return;
        }
        const classKey = boat.classKey.toUpperCase();
        const labelKey = boat.label.trim().toUpperCase();
        const option =
          classLookupMaps.byKey.get(classKey) ??
          classLookupMaps.byLabel.get(labelKey) ??
          null;
        if (!option) {
          return;
        }
        const canonicalKey = option.key.trim().toUpperCase();
        if (preferredKeys.has(canonicalKey)) {
          return;
        }
        preferredKeys.add(canonicalKey);
        const sailNumberSuffix = boat.sailNumber ? ` · Sail #${boat.sailNumber}` : "";
        preferred.push({ ...option, label: `${option.label}${sailNumberSuffix}` });
      });

      const remaining = classOptions.filter((option) => {
        const key = option.key.trim().toUpperCase();
        return !preferredKeys.has(key);
      });

      return {
        preferred,
        remaining,
      };
    },
    [classLookupMaps, classOptions, getBoatsForNames],
  );

  const scheduleOptions = useMemo(
    () =>
      scheduledRaces.map((race) => ({
        id: race.id,
        label: `${formatDisplayDate(race.date)} — ${race.series} ${
          race.raceNumber != null ? `#${race.raceNumber} ${race.race}` : race.race
        }${race.startTime ? ` (${toTimeInputValue(race.startTime)})` : ""}`.trim(),
      })),
    [scheduledRaces],
  );

  const handleRowChange = useCallback(
    (id: string, key: keyof EntryRow, value: string) => {
      setRows((current: EntryRow[]) =>
        current.map((row: EntryRow) => {
          if (row.id !== id) {
            return row;
          }

          if (key === "helm" || key === "crew") {
            const nextHelm = key === "helm" ? value : row.helm;
            const nextCrew = key === "crew" ? value : row.crew;
            const lookup = getBoatLookupForNames(nextHelm, nextCrew);
            const dinghyKey = row.dinghy?.toUpperCase?.() || "";
            const match = dinghyKey ? lookup.get(dinghyKey) : undefined;
            const next: EntryRow = {
              ...row,
              [key]: value,
            };
            if (match?.sailNumber) {
              next.sailNumber = match.sailNumber;
            }
            return next;
          }

          if (key === "dinghy") {
            const canonical = value.toUpperCase();
            const lookup = getBoatLookupForNames(row.helm, row.crew);
            const match = lookup.get(canonical);
            const next: EntryRow = {
              ...row,
              dinghy: canonical,
            };
            if (match?.sailNumber) {
              next.sailNumber = match.sailNumber;
            }
            return next;
          }

          return { ...row, [key]: value };
        }),
      );
    },
    [getBoatLookupForNames],
  );

  const removeRow = (id: string) => {
    setRows((current: EntryRow[]) => current.filter((row: EntryRow) => row.id !== id));
  };

  const addRow = () => {
    setRows((current: EntryRow[]) => [...current, blankRow()]);
  };

  const reset = () => {
    setRows(() => Array.from({ length: 10 }, blankRow));
    setResults(null);
    setErrorMessage(null);
    setSelectedScheduleId("");
  };

  const applyScheduledRace = () => {
    if (!selectedScheduleId) {
      return;
    }
    const selection = scheduledRaces.find((race) => race.id === selectedScheduleId);
    if (!selection) {
      return;
    }

    const raceNumberValue =
      selection.raceNumber != null && !Number.isNaN(selection.raceNumber)
        ? String(selection.raceNumber)
        : "";
    const dateValue = toDateInputValue(selection.date) || metadata.date;
    const startTimeValue = toTimeInputValue(selection.startTime);

    setMetadata((current: MetadataState) => ({
      ...current,
      series: selection.series ?? current.series,
      race: selection.race ?? current.race,
      raceNumber: raceNumberValue,
      date: dateValue,
      startTime: startTimeValue,
      raceOfficer: selection.raceOfficer?.trim() ?? current.raceOfficer,
    }));
  };

  const handleScore = async () => {
    setIsScoring(true);
    setErrorMessage(null);
    try {
      const trimmedSeries = metadata.series.trim();
      const trimmedRace = metadata.race.trim();
      const trimmedRaceOfficer = metadata.raceOfficer.trim();
      const raceNumberValue = metadata.raceNumber.trim();
      const startTimeValue = metadata.startTime.trim();
      const parsedRaceNumber = raceNumberValue ? Number.parseInt(raceNumberValue, 10) : null;
      const raceNumber =
        parsedRaceNumber !== null && !Number.isNaN(parsedRaceNumber) ? parsedRaceNumber : null;
      const metadataPayload = {
        series: trimmedSeries,
        race: trimmedRace,
        raceOfficer: trimmedRaceOfficer,
        date: metadata.date,
        raceNumber,
        startTime: startTimeValue || null,
      };

      const payload = {
        metadata: metadataPayload,
        entries: rows
          .filter(
            (row: EntryRow) =>
              row.helm ||
              row.crew ||
              row.dinghy ||
              row.sailNumber ||
              row.laps ||
              row.timeSeconds,
          )
          .map((row: EntryRow) => {
            const sailNumber = row.sailNumber.trim();
            const helm = row.helm.trim();
            const crew = row.crew.trim();
            const dinghy = row.dinghy.trim().toUpperCase();
            return {
              entryId: row.entryId || null,
              helm,
              crew,
              dinghy,
              sailNumber: sailNumber ? sailNumber.toUpperCase() : null,
              personal: row.personal ? parseInt(row.personal, 10) : 0,
              laps: row.laps ? parseInt(row.laps, 10) : null,
              timeSeconds: row.timeSeconds ? parseInt(row.timeSeconds, 10) : null,
              finCode: row.finCode ? row.finCode.toUpperCase() : null,
            };
          }),
      };
      const response = await fetch(`${API_BASE}/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail.detail as string) ?? "Scoring failed");
      }
      const scored = (await response.json()) as ScoreResponse;
      setResults(scored);
    } catch (error) {
      setResults(null);
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsScoring(false);
    }
  };

  const downloadHtml = () => {
    if (!results?.html) return;
    const blob = new Blob([results.html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${results.metadata.filename}.html`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className={styles.container}>
      <header className={styles.header}>
        <div>
          <h1>SWSC Race Sheet</h1>
          <p className={styles.tagline}>Capture results, apply PY scoring, and publish the sheet from any device.</p>
        </div>
        <div className={styles.headerActions}>
          <Link href="/portal" className={styles.linkButton}>
            Sign on portal
          </Link>
          <Link href="/standings" className={styles.linkButton}>
            View standings
          </Link>
          <Link href="/admin/races" className={styles.linkButton}>
            Manage schedule
          </Link>
          <Link href="/admin/series" className={styles.linkButton}>
            Manage series
          </Link>
        </div>
      </header>

      <section className={styles.card}>
        <h2>Race details</h2>
        <div className={styles.schedulePickerBlock}>
          <label>
            Scheduled race
            <div className={styles.schedulePickerControls}>
              <select
                value={selectedScheduleId}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setSelectedScheduleId(event.target.value)
                }
              >
                <option value="">
                  {scheduleLoading ? "Loading races…" : "Select a scheduled race"}
                </option>
                {scheduleOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className={styles.ghostButton}
                onClick={applyScheduledRace}
                disabled={!selectedScheduleId}
              >
                Apply
              </button>
            </div>
          </label>
          {scheduleError && (
            <p className={styles.error}>Failed to load scheduled races: {scheduleError.message}</p>
          )}
          {!scheduleError && !scheduleLoading && !scheduleOptions.length && (
            <p className={styles.muted}>No upcoming scheduled races found.</p>
          )}
        </div>
        <div className={styles.formRow}>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Series</span>
            <span className={styles.readOnlyValue}>{metadata.series || "—"}</span>
          </div>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Race</span>
            <span className={styles.readOnlyValue}>{metadata.race || "—"}</span>
          </div>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Race number</span>
            <span className={styles.readOnlyValue}>{metadata.raceNumber || "—"}</span>
          </div>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Date</span>
            <span className={styles.readOnlyValue}>{metadata.date || "—"}</span>
          </div>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Start time</span>
            <span className={styles.readOnlyValue}>{metadata.startTime || "—"}</span>
          </div>
          <div className={styles.readOnlyField}>
            <span className={styles.readOnlyLabel}>Race Officer</span>
            <span className={styles.readOnlyValue}>{metadata.raceOfficer || "—"}</span>
          </div>
        </div>
      </section>

      <section className={styles.card}>
        <div className={styles.sectionHeader}>
          <h2>Entries</h2>
          <div className={styles.sectionActions}>
            <button type="button" onClick={addRow}>
              Add row
            </button>
            <button type="button" onClick={reset} className={styles.ghostButton}>
              Reset grid
            </button>
          </div>
        </div>

        {referenceError && (
          <p className={styles.error}>Failed to load reference data: {referenceError.message}</p>
        )}
        {referenceLoading && <p>Loading reference data…</p>}
        {rosterError && <p className={styles.error}>Failed to load member profiles: {rosterError.message}</p>}
        {!rosterError && rosterLoading && <p className={styles.muted}>Loading member profiles…</p>}
        {rosterNameOptions.length > 0 && (
          <datalist id={PEOPLE_DATALIST_ID}>
            {rosterNameOptions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        )}

        <div className={styles.tableWrapper}>
          <table className={styles.entryTable}>
            <thead>
              <tr>
                <th>Helm</th>
                <th>Crew</th>
                <th>Class</th>
                <th>Sail #</th>
                <th>Laps</th>
                <th>Time (s)</th>
                <th>Code</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const { preferred, remaining } = getClassDropdownOptions(row.helm, row.crew);
                return (
                  <tr key={row.id}>
                  <td>
                    <input
                      list={rosterNameOptions.length ? PEOPLE_DATALIST_ID : undefined}
                      value={row.helm}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        handleRowChange(row.id, "helm", event.target.value)
                      }
                      placeholder="Helm name"
                    />
                  </td>
                  <td>
                    <input
                      list={rosterNameOptions.length ? PEOPLE_DATALIST_ID : undefined}
                      value={row.crew}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        handleRowChange(row.id, "crew", event.target.value)
                      }
                      placeholder="Crew name"
                    />
                  </td>
                  <td>
                    <select
                      value={row.dinghy}
                      onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                        handleRowChange(row.id, "dinghy", event.target.value)
                      }
                    >
                      <option value="">Select class</option>
                      {preferred.map((option) => (
                        <option key={`${option.key}-preferred`} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                      {preferred.length > 0 && remaining.length > 0 && (
                        <option key="divider" value="" disabled>
                          ─────────────
                        </option>
                      )}
                      {remaining.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      value={row.sailNumber}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        handleRowChange(row.id, "sailNumber", event.target.value)
                      }
                      placeholder="Sail number"
                    />
                  </td>
                  <td>
                    <input
                      value={row.laps}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        handleRowChange(row.id, "laps", event.target.value)
                      }
                      inputMode="numeric"
                      pattern="[0-9]*"
                    />
                  </td>
                  <td>
                    <input
                      value={row.timeSeconds}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        handleRowChange(row.id, "timeSeconds", event.target.value)
                      }
                      inputMode="numeric"
                      pattern="[0-9]*"
                    />
                  </td>
                  <td>
                    <select
                      value={row.finCode}
                      onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                        handleRowChange(row.id, "finCode", event.target.value)
                      }
                    >
                      {finCodes.map((code) => (
                        <option key={code} value={code}>
                          {code || ""}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className={styles.rowActions}>
                    <button
                      type="button"
                      onClick={() => removeRow(row.id)}
                      className={clsx(styles.ghostButton, styles.danger)}
                      aria-label="Remove row"
                    >
                      ×
                    </button>
                  </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.actions}>
        <button type="button" onClick={handleScore} disabled={isScoring}>
          {isScoring ? "Scoring…" : "Score race"}
        </button>
        {results?.html && (
          <button type="button" className={styles.ghostButton} onClick={downloadHtml}>
            Download HTML
          </button>
        )}
      </section>

      {errorMessage && <p className={styles.error}>{errorMessage}</p>}

      {results && (
        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <h2>Results</h2>
            <div className={styles.sectionMeta}>
              <span>{results.metadata.series}</span>
              <span>{results.metadata.race}</span>
              {results.metadata.raceNumber != null && (
                <span>{`Race #${results.metadata.raceNumber}`}</span>
              )}
              {results.metadata.startTime && (
                <span>{`Start ${results.metadata.startTime}`}</span>
              )}
              <span>{results.metadata.date}</span>
              <span>{`RO ${results.metadata.raceOfficer}`}</span>
            </div>
          </div>

          <div className={styles.resultsGrid}>
            <div>
              <h3>Portsmouth Yardstick</h3>
              <table className={styles.resultTable}>
                <thead>
                  <tr>
                    <th>Entry ID</th>
                    <th>Helm/Crew</th>
                    <th>Class</th>
                    <th>PY</th>
                    <th>Laps</th>
                    <th>Time</th>
                    <th>Corrected</th>
                    <th>Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {results.pyResults.map((row: PyResult, index: number) => (
                    <tr key={`${row.entryId}-${index}`}>
                      <td>{row.entryId}</td>
                      <td>
                        <span className={styles.helm}>{row.helm}</span>
                        <span className={styles.crew}>{row.crew}</span>
                      </td>
                      <td>{row.dinghy}</td>
                      <td>{row.py}</td>
                      <td>{row.laps}</td>
                      <td>{row.timeSeconds}</td>
                      <td>{row.finCode ? row.finCode : row.corrected ?? ""}</td>
                      <td>{row.rank ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <h3>Personal handicap</h3>
              <table className={styles.resultTable}>
                <thead>
                  <tr>
                    <th>Entry ID</th>
                    <th>Helm/Crew</th>
                    <th>Personal</th>
                    <th>Corrected</th>
                    <th>Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {results.personalResults.map((row, index) => (
                    <tr key={`${row.entryId}-${index}`}>
                      <td>{row.entryId}</td>
                      <td>
                        <span className={styles.helm}>{row.helm}</span>
                        <span className={styles.crew}>{row.crew}</span>
                      </td>
                      <td>{row.personalHandicap}</td>
                      <td>{row.corrected ?? ""}</td>
                      <td>{row.rank ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <details className={styles.summaryDetails}>
            <summary>Raw summary</summary>
            <pre>{results.summary}</pre>
          </details>
        </section>
      )}
    </main>
  );
}
