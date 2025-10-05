"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { clsx } from "clsx";
import type { Session } from "@supabase/supabase-js";

import { API_BASE, fetcher } from "../api-client";
import {
  type PortalCrewMember,
  type PortalRaceSignon,
  type PortalRaceSignonResponse,
  type PortalSeriesEntry,
  type PortalSeriesEntryResponse,
  type Series,
  type SeriesListResponse,
  type ScheduledRace,
  type ScheduledRacesResponse,
} from "../types";
import { getSupabaseClient } from "../../lib/supabaseClient";
import styles from "./page.module.css";

interface ReferenceClassOption {
  key: string;
  label: string;
}

interface ReferenceData {
  classOptions: ReferenceClassOption[];
}

interface ProfileRosterEntry {
  id: string;
  helm: string;
  crew?: string | null;
}

interface ProfileRosterResponse {
  profiles: ProfileRosterEntry[];
}

const PEOPLE_DATALIST_ID = "portal-people-options";

interface AuthFormState {
  email: string;
  password: string;
}

const buildCrewPayload = (names: string[]): PortalCrewMember[] =>
  names
    .map((value) => value.trim())
    .filter((value) => value.length > 0)
    .map((name) => ({ name }));

const inferDisplayName = (session: Session | null): string => {
  if (!session?.user) return "";
  const metadata = session.user.user_metadata ?? {};
  const candidate = metadata.full_name || metadata.fullName || metadata.displayName || metadata.display_name;
  if (typeof candidate === "string" && candidate.trim()) {
    return candidate.trim();
  }
  if (session.user.email) {
    return session.user.email.split("@")[0] ?? session.user.email;
  }
  return "";
};

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function PortalPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [authForm, setAuthForm] = useState<AuthFormState>({ email: "", password: "" });
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  const [helmName, setHelmName] = useState<string>("");
  const [crewInputs, setCrewInputs] = useState<string[]>([""]);
  const [boatClass, setBoatClass] = useState<string>("");
  const [sailNumber, setSailNumber] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  const [seriesEntrySelections, setSeriesEntrySelections] = useState<Set<string>>(() => new Set());
  const [selectedSeriesForRaces, setSelectedSeriesForRaces] = useState<string>("");
  const [selectedRaceIds, setSelectedRaceIds] = useState<Set<string>>(() => new Set());

  const [seriesEntryStatus, setSeriesEntryStatus] = useState<{ type: "success" | "error" | null; message: string | null }>({
    type: null,
    message: null,
  });
  const [signonStatus, setSignonStatus] = useState<{ type: "success" | "error" | null; message: string | null }>({
    type: null,
    message: null,
  });
  const [recentEntries, setRecentEntries] = useState<PortalSeriesEntry[]>([]);
  const [recentSignons, setRecentSignons] = useState<PortalRaceSignon[]>([]);
  const [isSubmittingEntries, setIsSubmittingEntries] = useState(false);
  const [isSubmittingSignons, setIsSubmittingSignons] = useState(false);

  const { mutate } = useSWRConfig();

  useEffect(() => {
    const supabase = getSupabaseClient();
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session ?? null);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession ?? null);
    });
    return () => {
      data.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    const inferred = inferDisplayName(session);
    if (inferred && !helmName) {
      setHelmName(inferred);
    }
  }, [session, helmName]);

  const { data: seriesData } = useSWR<SeriesListResponse>("/series", fetcher);
  const { data: scheduleData } = useSWR<ScheduledRacesResponse>("/scheduled-races?includePast=false", fetcher);
  const { data: referenceData } = useSWR<ReferenceData>("/reference", fetcher);
  const { data: rosterData } = useSWR<ProfileRosterResponse>("/profiles-roster", fetcher);

  const rosterNameOptions = useMemo(() => {
    const seen = new Set<string>();
    const names: string[] = [];
    rosterData?.profiles?.forEach((profile) => {
      [profile.helm, profile.crew].forEach((value) => {
        const name = (value ?? "").trim();
        if (!name) return;
        const key = name.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        names.push(name);
      });
    });
    names.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return names;
  }, [rosterData]);

  const classOptions = useMemo(() => referenceData?.classOptions ?? [], [referenceData]);

  const seriesOptions = useMemo<Series[]>(() => seriesData?.series ?? [], [seriesData]);

  const selectedSeriesObject = useMemo(
    () => seriesOptions.find((item) => item.id === selectedSeriesForRaces) ?? null,
    [seriesOptions, selectedSeriesForRaces],
  );

  useEffect(() => {
    if (!selectedSeriesForRaces && seriesOptions.length) {
      setSelectedSeriesForRaces(seriesOptions[0].id);
    }
  }, [seriesOptions, selectedSeriesForRaces]);

  const todaysDate = todayIso();

  const todaysRaces = useMemo(() => {
    const races = scheduleData?.races ?? [];
    return races.filter((race) => race.date === todaysDate);
  }, [scheduleData, todaysDate]);

  const racesForSelectedSeries = useMemo(() => {
    if (!selectedSeriesObject) {
      return [] as ScheduledRace[];
    }
    const targetCode = (selectedSeriesObject.code ?? "").toUpperCase();
    return todaysRaces.filter((race) => (race.seriesCode ?? "").toUpperCase() === targetCode);
  }, [todaysRaces, selectedSeriesObject]);

  const handleAuthChange = (key: keyof AuthFormState) => (event: ChangeEvent<HTMLInputElement>) => {
    setAuthForm((current) => ({ ...current, [key]: event.target.value }));
    setAuthError(null);
  };

  const handleSignIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthError(null);
    setAuthLoading(true);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.signInWithPassword({
        email: authForm.email.trim(),
        password: authForm.password,
      });
      if (error) {
        throw new Error(error.message);
      }
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Unable to sign in. Please try again.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    setAuthForm({ email: "", password: "" });
    setHelmName("");
    setCrewInputs([""]);
    setSeriesEntrySelections(new Set());
    setSelectedRaceIds(new Set());
  };

  const toggleSeriesSelection = (seriesId: string) => {
    setSeriesEntrySelections((current) => {
      const next = new Set(current);
      if (next.has(seriesId)) {
        next.delete(seriesId);
      } else {
        next.add(seriesId);
      }
      return next;
    });
    setSeriesEntryStatus({ type: null, message: null });
  };

  const toggleRaceSelection = (raceId: string) => {
    setSelectedRaceIds((current) => {
      const next = new Set(current);
      if (next.has(raceId)) {
        next.delete(raceId);
      } else {
        next.add(raceId);
      }
      return next;
    });
    setSignonStatus({ type: null, message: null });
  };

  const updateCrewMember = (index: number, value: string) => {
    setCrewInputs((current) => current.map((entry, idx) => (idx === index ? value : entry)));
  };

  const addCrewField = () => {
    setCrewInputs((current) => (current.length >= 3 ? current : [...current, ""]));
  };

  const removeCrewField = (index: number) => {
    setCrewInputs((current) => current.filter((_, idx) => idx !== index));
  };

  const crewPayload = useMemo(() => buildCrewPayload(crewInputs), [crewInputs]);

  const commonPayloadFields = () => ({
    helmName: helmName.trim(),
    helmProfileId: session?.user?.id ?? null,
    crew: crewPayload,
    boatClass: boatClass.trim() || undefined,
    sailNumber: sailNumber.trim() || undefined,
    notes: notes.trim() || undefined,
  });

  const handleSubmitSeriesEntries = async () => {
    if (!session) {
      setSeriesEntryStatus({ type: "error", message: "Please sign in before entering a series." });
      return;
    }
    if (!helmName.trim()) {
      setSeriesEntryStatus({ type: "error", message: "Please add the helm name before submitting." });
      return;
    }
    if (!seriesEntrySelections.size) {
      setSeriesEntryStatus({ type: "error", message: "Select at least one series to enter." });
      return;
    }

    setIsSubmittingEntries(true);
    setSeriesEntryStatus({ type: null, message: null });
    try {
      const payload = {
        entries: Array.from(seriesEntrySelections).map((seriesId) => ({
          seriesId,
          ...commonPayloadFields(),
        })),
      };
      const response = await fetch(`${API_BASE}/portal/series-entries`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail?.detail as string) ?? "Failed to enter series");
      }
      const created = (await response.json()) as PortalSeriesEntryResponse;
      setRecentEntries(created.entries);
      setSeriesEntryStatus({ type: "success", message: `Registered ${created.entries.length} entr${created.entries.length === 1 ? "y" : "ies"}.` });
      await mutate("/series");
    } catch (error) {
      setSeriesEntryStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Unexpected error while entering series.",
      });
    } finally {
      setIsSubmittingEntries(false);
    }
  };

  const handleSubmitSignons = async () => {
    if (!session) {
      setSignonStatus({ type: "error", message: "Please sign in before signing on." });
      return;
    }
    if (!helmName.trim()) {
      setSignonStatus({ type: "error", message: "Please add the helm name before submitting." });
      return;
    }
    if (!selectedSeriesForRaces) {
      setSignonStatus({ type: "error", message: "Choose which series you're racing in." });
      return;
    }
    if (!selectedRaceIds.size) {
      setSignonStatus({ type: "error", message: "Select at least one race for today." });
      return;
    }

    setIsSubmittingSignons(true);
    setSignonStatus({ type: null, message: null });
    try {
      const payload = {
        seriesId: selectedSeriesForRaces,
        scheduledRaceIds: Array.from(selectedRaceIds),
        ...commonPayloadFields(),
      };
      const response = await fetch(`${API_BASE}/portal/signons`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error((detail?.detail as string) ?? "Failed to submit sign-on");
      }
      const created = (await response.json()) as PortalRaceSignonResponse;
      setRecentSignons(created.signons);
      setSignonStatus({
        type: "success",
        message: `Submitted sign-on for ${created.signons.length} rac${created.signons.length === 1 ? "e" : "es"}.`,
      });
      setSelectedRaceIds(new Set());
      await mutate("/scheduled-races?includePast=false");
    } catch (error) {
      setSignonStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Unexpected error while signing on.",
      });
    } finally {
      setIsSubmittingSignons(false);
    }
  };

  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        <header className={styles.header}>
          <div>
            <h1>Race day portal</h1>
            <p>Sign into Supabase, register for series, and sign on for today's racing in one place.</p>
          </div>
          <div className={styles.headerLinks}>
            <Link href="/" className={styles.linkButton}>
              Score a race
            </Link>
            <Link href="/standings" className={styles.linkButton}>
              View standings
            </Link>
          </div>
        </header>

        {!session ? (
          <section className={clsx(styles.card, styles.authCard)}>
            <h2>Sign in</h2>
            <form onSubmit={handleSignIn} className={styles.authForm}>
              <label>
                Email
                <input type="email" value={authForm.email} onChange={handleAuthChange("email")} required autoComplete="email" />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={authForm.password}
                  onChange={handleAuthChange("password")}
                  required
                  autoComplete="current-password"
                />
              </label>
              {authError && <p className={styles.error}>{authError}</p>}
              <button type="submit" className={styles.primaryButton} disabled={authLoading}>
                {authLoading ? "Signing in…" : "Sign in"}
              </button>
            </form>
            <p className={styles.muted}>Need an account? Ask the results team to create one for you.</p>
          </section>
        ) : (
          <section className={clsx(styles.card, styles.authCard)}>
            <div className={styles.signedInHeader}>
              <div>
                <h2>Signed in</h2>
                <p className={styles.muted}>Welcome back {helmName || session.user.email}</p>
              </div>
              <button type="button" onClick={handleSignOut} className={styles.secondaryButton}>
                Sign out
              </button>
            </div>
          </section>
        )}

        <section className={styles.card}>
          <h2>Boat & crew details</h2>
          <div className={styles.formGrid}>
            <label>
              Helm name
              <input
                value={helmName}
                onChange={(event) => setHelmName(event.target.value)}
                placeholder="Helm name"
                list={PEOPLE_DATALIST_ID}
              />
            </label>
            <label>
              Sail number
              <input value={sailNumber} onChange={(event) => setSailNumber(event.target.value)} placeholder="Optional" />
            </label>
            <label>
              Boat class
              <select value={boatClass} onChange={(event) => setBoatClass(event.target.value)}>
                <option value="">Select a class…</option>
                {classOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className={styles.crewSection}>
            <span>Crew</span>
            <div className={styles.crewList}>
              {crewInputs.map((value, index) => (
                <div key={`crew-${index}`} className={styles.crewRow}>
                  <input
                    value={value}
                    onChange={(event) => updateCrewMember(index, event.target.value)}
                    placeholder="Crew name"
                    list={PEOPLE_DATALIST_ID}
                  />
                  {crewInputs.length > 1 && (
                    <button type="button" className={styles.iconButton} onClick={() => removeCrewField(index)}>
                      Remove
                    </button>
                  )}
                </div>
              ))}
            </div>
            {crewInputs.length < 3 && (
              <button type="button" className={styles.secondaryButton} onClick={addCrewField}>
                Add crew member
              </button>
            )}
          </div>
          <label className={styles.notesField}>
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional notes for the duty team" />
          </label>
        </section>

        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <h2>Enter a series</h2>
            <p className={styles.muted}>Register for the series leaderboard so your results count across the season.</p>
          </div>
          <div className={styles.seriesList}>
            {seriesOptions.map((series) => (
              <label key={series.id} className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={seriesEntrySelections.has(series.id)}
                  onChange={() => toggleSeriesSelection(series.id)}
                />
                <span>
                  {series.title}
                  {series.code ? ` (${series.code})` : ""}
                </span>
              </label>
            ))}
            {!seriesOptions.length && <p className={styles.muted}>No series have been published yet.</p>}
          </div>
          {seriesEntryStatus.message && (
            <p className={clsx(styles.statusMessage, seriesEntryStatus.type === "error" ? styles.error : styles.success)}>
              {seriesEntryStatus.message}
            </p>
          )}
          <div className={styles.buttonRow}>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={handleSubmitSeriesEntries}
              disabled={isSubmittingEntries}
            >
              {isSubmittingEntries ? "Submitting…" : "Enter selected series"}
            </button>
          </div>
          {recentEntries.length > 0 && (
            <ul className={styles.resultList}>
              {recentEntries.map((entry) => (
                <li key={entry.id}>
                  <span className={styles.resultTitle}>{entry.series.title || entry.series.code || "Series"}</span>
                  <span className={styles.resultMeta}>
                    Submitted {new Date(entry.createdAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <h2>Sign on for today</h2>
            <p className={styles.muted}>Pick today’s series and races – perfect for cup days with multiple starts.</p>
          </div>
          <label className={styles.seriesSelector}>
            Series for today
            <select value={selectedSeriesForRaces} onChange={(event) => setSelectedSeriesForRaces(event.target.value)}>
              {seriesOptions.map((series) => (
                <option key={series.id} value={series.id}>
                  {series.title}
                  {series.code ? ` (${series.code})` : ""}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.raceList}>
            {racesForSelectedSeries.map((race) => (
              <label key={race.id} className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={selectedRaceIds.has(race.id)}
                  onChange={() => toggleRaceSelection(race.id)}
                />
                <span>
                  {race.race}
                  {race.raceNumber ? ` (#${race.raceNumber})` : ""}
                  {race.startTime ? ` · ${new Date(race.startTime).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}` : ""}
                </span>
              </label>
            ))}
            {racesForSelectedSeries.length === 0 && (
              <p className={styles.muted}>No races scheduled for today under this series.</p>
            )}
          </div>
          {signonStatus.message && (
            <p className={clsx(styles.statusMessage, signonStatus.type === "error" ? styles.error : styles.success)}>
              {signonStatus.message}
            </p>
          )}
          <div className={styles.buttonRow}>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={handleSubmitSignons}
              disabled={isSubmittingSignons}
            >
              {isSubmittingSignons ? "Submitting…" : "Sign on for selected races"}
            </button>
          </div>
          {recentSignons.length > 0 && (
            <ul className={styles.resultList}>
              {recentSignons.map((signon) => (
                <li key={signon.id}>
                  <span className={styles.resultTitle}>{signon.race.label}</span>
                  <span className={styles.resultMeta}>{signon.race.date}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <datalist id={PEOPLE_DATALIST_ID}>
        {rosterNameOptions.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>
    </main>
  );
}
