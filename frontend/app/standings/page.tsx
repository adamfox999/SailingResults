"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";

import { fetcher } from "../api-client";
import {
  type Series,
  type SeriesCompetitorStanding,
  type SeriesListResponse,
  type SeriesRaceSummary,
  type SeriesStandingsResponse,
  type SeriesStandingsSummary,
} from "../types";
import { formatDisplayDate } from "../utils/datetime";
import styles from "./page.module.css";

const formatScoreValue = (value?: number | null): string => {
  if (value == null) {
    return "—";
  }
  const rounded = Math.round(value * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${Math.round(rounded)}`;
  }
  return rounded.toFixed(1);
};

const buildSeriesRange = (series: SeriesStandingsSummary): string => {
  const { startDate, endDate } = series;
  const formattedStart = startDate ? formatDisplayDate(startDate) : null;
  const formattedEnd = endDate ? formatDisplayDate(endDate) : null;

  if (formattedStart && formattedEnd) {
    if (formattedStart === formattedEnd) {
      return formattedStart;
    }
    return `${formattedStart} – ${formattedEnd}`;
  }
  if (formattedStart) {
    return `Starts ${formattedStart}`;
  }
  if (formattedEnd) {
    return `Ends ${formattedEnd}`;
  }
  return "Dates not set";
};

interface StandingsTableProps {
  title: string;
  subtitle: string;
  races: SeriesRaceSummary[];
  results: SeriesCompetitorStanding[];
  dncValue: number;
}

const StandingsTable = ({ title, subtitle, races, results, dncValue }: StandingsTableProps) => {
  if (!races.length) {
    return (
      <section className={styles.tableCard}>
        <div className={styles.tableHeader}>
          <h3>{title}</h3>
          <span>{subtitle}</span>
        </div>
        <div className={styles.noRaces}>No races have been scored for this series yet.</div>
      </section>
    );
  }

  if (!results.length) {
    return (
      <section className={styles.tableCard}>
        <div className={styles.tableHeader}>
          <h3>{title}</h3>
          <span>{subtitle}</span>
        </div>
        <div className={styles.noRaces}>No competitors have recorded finishes yet.</div>
      </section>
    );
  }

  return (
    <section className={styles.tableCard}>
      <div className={styles.tableHeader}>
        <h3>{title}</h3>
        <span>{subtitle}</span>
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.rankCell}>Rank</th>
            <th className={styles.nameCell}>Helm</th>
            <th className={styles.boatCell}>Boat(s)</th>
            <th className={styles.crewCell}>Crew</th>
            {races.map((race) => (
              <th key={race.id}>{race.label}</th>
            ))}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {results.map((competitor) => (
            <tr key={competitor.helm}>
              <td className={styles.rankCell}>{competitor.rank ?? "—"}</td>
              <td className={styles.nameCell}>{competitor.helm}</td>
              <td className={styles.boatCell}>
                {competitor.boats.length ? competitor.boats.join(", ") : "—"}
              </td>
              <td className={styles.crewCell}>
                {competitor.crews.length ? competitor.crews.join(", ") : "—"}
              </td>
              {competitor.scores.perRace.map((cell, idx) => (
                <td
                  key={`${competitor.helm}-${idx}`}
                  className={clsx(styles.scoreCell, {
                    [styles.counted]: cell.counted,
                    [styles.dnc]: cell.isDnc,
                  })}
                  title={cell.isDnc ? `Did not compete · counts as ${dncValue}` : cell.value != null ? `Score ${formatScoreValue(cell.value)}` : "Score unavailable"}
                >
                  {cell.isDnc ? "DNC" : formatScoreValue(cell.value)}
                </td>
              ))}
              <td className={clsx(styles.scoreCell, styles.totalCell)}>
                {competitor.scores.total == null ? "—" : formatScoreValue(competitor.scores.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
};

export default function SeriesStandingsPage() {
  const [selectedSeriesId, setSelectedSeriesId] = useState<string>("");

  const {
    data: seriesData,
    error: seriesError,
    isLoading: seriesLoading,
  } = useSWR<SeriesListResponse>("/series", fetcher);

  const seriesOptions = useMemo(() => {
    if (!seriesData?.series?.length) {
      return [] as Series[];
    }
    return [...seriesData.series].sort((a, b) => a.title.localeCompare(b.title));
  }, [seriesData]);

  useEffect(() => {
    if (!selectedSeriesId && seriesOptions.length) {
      setSelectedSeriesId(seriesOptions[0].id);
    }
  }, [seriesOptions, selectedSeriesId]);

  const standingsKey = selectedSeriesId ? `/series/${selectedSeriesId}/standings` : null;

  const {
    data: standingsData,
    error: standingsError,
    isLoading: standingsLoading,
  } = useSWR<SeriesStandingsResponse>(standingsKey, fetcher);

  const summary = standingsData?.series ?? null;
  const races = standingsData?.races ?? [];

  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        <header className={styles.header}>
          <div className={styles.headerTop}>
            <div className={styles.headerTitle}>
              <h1>Series standings</h1>
              <p>Select a series to review the current leaderboard, including discard rules and DNC handling.</p>
            </div>
            <div className={styles.headerActions}>
              <Link href="/" className={styles.linkButton}>
                Score a race
              </Link>
              <Link href="/portal" className={styles.linkButton}>
                Sign on portal
              </Link>
              <Link href="/admin/series" className={styles.linkButton}>
                Manage series
              </Link>
            </div>
          </div>
        </header>

        <section className={styles.selectorCard}>
          <label className={styles.selectorLabel}>
            <span>Choose a series</span>
            <select
              className={styles.seriesSelect}
              value={selectedSeriesId}
              onChange={(event) => setSelectedSeriesId(event.target.value)}
              disabled={seriesLoading || !seriesOptions.length}
            >
              <option value="">
                {seriesLoading ? "Loading series…" : "Select a series"}
              </option>
              {seriesOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.title}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.statusRow}>
            {seriesError && <div className={styles.error}>Failed to load series: {seriesError.message}</div>}
            {!seriesError && !seriesLoading && !seriesOptions.length && (
              <div className={styles.empty}>No series have been created yet.</div>
            )}
            {standingsError && <div className={styles.error}>Failed to load standings: {standingsError.message}</div>}
            {standingsLoading && selectedSeriesId && <div className={styles.loading}>Loading standings…</div>}
          </div>
        </section>

        {summary && (
          <section className={styles.summaryCard}>
            <div className={styles.summaryHeader}>
              <h2>{summary.title}</h2>
              <span className={styles.summaryBadge}>{buildSeriesRange(summary)}</span>
            </div>
            <div className={styles.summaryStats}>
              <div className={styles.summaryItem}>
                <span>Code</span>
                <strong>{summary.code}</strong>
              </div>
              <div className={styles.summaryItem}>
                <span>Races sailed</span>
                <strong>{summary.raceCount}</strong>
              </div>
              <div className={styles.summaryItem}>
                <span>Competitors</span>
                <strong>{summary.competitorCount}</strong>
              </div>
              <div className={styles.summaryItem}>
                <span>To count</span>
                <strong>{summary.countAll ? "All races" : summary.toCount}</strong>
              </div>
              <div className={styles.summaryItem}>
                <span>DNC score</span>
                <strong>{summary.dncValue}</strong>
              </div>
            </div>
          </section>
        )}

        {standingsData && (
          <section className={styles.tablesSection}>
            <StandingsTable
              title="PY handicap"
              subtitle="Official race finishes"
              races={races}
              results={standingsData.pyResults}
              dncValue={summary?.dncValue ?? 0}
            />
            <StandingsTable
              title="Personal handicap"
              subtitle="Personal handicap scores"
              races={races}
              results={standingsData.personalResults}
              dncValue={summary?.dncValue ?? 0}
            />
          </section>
        )}
      </div>
    </main>
  );
}
