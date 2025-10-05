export interface ScheduledRace {
  id: string;
  series: string;
  race: string;
  seriesCode?: string | null;
  raceNumber?: number | null;
  raceOfficer?: string | null;
  date: string;
  startTime?: string | null;
  notes?: string | null;
}

export interface ScheduledRacesResponse {
  races: ScheduledRace[];
}

export interface Series {
  id: string;
  code: string;
  title: string;
  startDate?: string | null;
  endDate?: string | null;
}

export interface SeriesListResponse {
  series: Series[];
}

export interface SeriesStandingsSummary extends Series {
  toCount: number;
  countAll: boolean;
  raceCount: number;
  competitorCount: number;
  dncValue: number;
}

export interface SeriesRaceSummary {
  id: string;
  label: string;
  raceNumber?: number | null;
  date?: string | null;
  startTime?: string | null;
}

export interface SeriesScoreCell {
  value?: number | null;
  isDnc: boolean;
  counted: boolean;
}

export interface SeriesScoreSummary {
  perRace: SeriesScoreCell[];
  total?: number | null;
}

export interface SeriesCompetitorStanding {
  helm: string;
  boats: string[];
  crews: string[];
  scores: SeriesScoreSummary;
  rank?: number | null;
}

export interface SeriesStandingsResponse {
  series: SeriesStandingsSummary;
  races: SeriesRaceSummary[];
  pyResults: SeriesCompetitorStanding[];
  personalResults: SeriesCompetitorStanding[];
}

export interface PortalCrewMember {
  profileId?: string | null;
  name: string;
}

export interface PortalSeriesSummary extends Series {
  startDate?: string | null;
  endDate?: string | null;
}

export interface PortalSeriesEntry {
  id: string;
  series: PortalSeriesSummary;
  helmName: string;
  helmProfileId?: string | null;
  crew: PortalCrewMember[];
  boatClass?: string | null;
  sailNumber?: string | null;
  notes?: string | null;
  submittedBy?: string | null;
  createdAt: string;
}

export interface PortalRaceSummary {
  id: string;
  label: string;
  date: string;
  startTime?: string | null;
  raceNumber?: number | null;
}

export interface PortalRaceSignon {
  id: string;
  series: PortalSeriesSummary;
  race: PortalRaceSummary;
  helmName: string;
  helmProfileId?: string | null;
  crew: PortalCrewMember[];
  boatClass?: string | null;
  sailNumber?: string | null;
  notes?: string | null;
  submittedBy?: string | null;
  createdAt: string;
}

export interface PortalSeriesEntryResponse {
  entries: PortalSeriesEntry[];
}

export interface PortalRaceSignonResponse {
  signons: PortalRaceSignon[];
}
