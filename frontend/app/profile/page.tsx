"use client";

import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import useSWR from "swr";
import type { Session } from "@supabase/supabase-js";
import clsx from "clsx";
import { getSupabaseClient } from "../../lib/supabaseClient";
import { fetcher } from "../api-client";
import styles from "./page.module.css";

interface BoatEntry {
  id: string;
  className: string;
  sailNumber: string;
}

interface ClassOption {
  key: string;
  label: string;
}

interface ReferenceData {
  classes: Record<string, number>;
  classOptions: ClassOption[];
  finCodes: string[];
}

interface ClassLookupEntry {
  key: string;
  label: string;
  py: number | null;
}

const BOAT_CLASS_DATALIST_ID = "profile-boat-class-options";

type AuthMode = "signIn" | "signUp";

const GENDER_CHOICES = ["female", "male"] as const;
type GenderChoice = (typeof GENDER_CHOICES)[number];
type GenderValue = "" | GenderChoice;

const GENDER_OPTIONS: Array<{ value: GenderChoice; label: string }> = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
];

const PROFILE_MIGRATION_MESSAGE =
  "Your Supabase `profiles` table is missing the latest columns. Run the SQL in web/README.md (Member profiles & Supabase auth) to add `date_of_birth`, `gender`, and `boats`.";

const extractSupabaseMessage = (error: unknown): string | null => {
  if (!error || typeof error !== "object") {
    return null;
  }

  if ("message" in error && typeof (error as { message?: unknown }).message === "string") {
    return ((error as { message?: string }).message ?? "").trim() || null;
  }

  if ("error_description" in error && typeof (error as { error_description?: unknown }).error_description === "string") {
    return ((error as { error_description?: string }).error_description ?? "").trim() || null;
  }

  if ("hint" in error && typeof (error as { hint?: unknown }).hint === "string") {
    return ((error as { hint?: string }).hint ?? "").trim() || null;
  }

  return null;
};

const normaliseGenderValue = (value: unknown): GenderValue => {
  if (typeof value !== "string") {
    return "";
  }

  const trimmed = value.trim().toLowerCase();
  return trimmed === "female" || trimmed === "male" ? (trimmed as GenderChoice) : "";
};

const generateBoat = (): BoatEntry => ({
  id: typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2, 10),
  className: "",
  sailNumber: "",
});

export default function ProfilePage() {
  const [configError, setConfigError] = useState<string | null>(null);
  const supabase = useMemo(() => {
    try {
      return getSupabaseClient();
    } catch (error) {
      console.error(error);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!supabase) {
      setConfigError("Supabase client is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
    }
  }, [supabase]);

  const [session, setSession] = useState<Session | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("signIn");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const [dateOfBirth, setDateOfBirth] = useState<string>("");
  const [gender, setGender] = useState<GenderValue>("");
  const [boats, setBoats] = useState<BoatEntry[]>([generateBoat()]);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profileSchemaIssue, setProfileSchemaIssue] = useState<string | null>(null);

  const { data: referenceData, error: referenceError } = useSWR<ReferenceData>("/reference", fetcher, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
  });

  const classOptions = useMemo(() => referenceData?.classOptions ?? [], [referenceData]);

  const classLookup = useMemo<Record<string, ClassLookupEntry>>(() => {
    if (!referenceData) {
      return {};
    }

    const lookup: Record<string, ClassLookupEntry> = {};
    const classesMap = referenceData.classes ?? {};
    const options = referenceData.classOptions ?? [];

    for (const option of options) {
      const canonicalKey = option.key.trim().toUpperCase();
      const labelKey = option.label.trim().toUpperCase();
      const pyValue = Object.prototype.hasOwnProperty.call(classesMap, canonicalKey)
        ? classesMap[canonicalKey]
        : null;
      const entry: ClassLookupEntry = {
        key: canonicalKey,
        label: option.label,
        py: pyValue != null ? Number(pyValue) : null,
      };
      lookup[canonicalKey] = entry;
      lookup[labelKey] = entry;
    }

    return lookup;
  }, [referenceData]);

  const isReferenceLoading = !referenceData && !referenceError;

  const normaliseDateForInput = useCallback((value: string | null | undefined) => {
    if (!value) {
      return "";
    }

    const trimmed = value.trim();
    if (!trimmed) {
      return "";
    }

    const isoMatch = /^\d{4}-\d{2}-\d{2}/.exec(trimmed);
    if (isoMatch && isoMatch[0]) {
      return isoMatch[0];
    }

    const parsed = new Date(trimmed);
    if (Number.isNaN(parsed.getTime())) {
      return "";
    }

    return parsed.toISOString().slice(0, 10);
  }, []);

  const todayIsoDate = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const normaliseBoatClassInput = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        return value;
      }

      const canonical = trimmed.toUpperCase();
      const match = classLookup[canonical];
      if (match) {
        return match.label;
      }

      return value;
    },
    [classLookup],
  );

  const resetProfileState = useCallback(() => {
    setDateOfBirth("");
    setGender("");
    setBoats([generateBoat()]);
    setProfileLoaded(false);
    setProfileSchemaIssue(null);
  }, []);

  const fetchProfile = useCallback(async (userId: string) => {
    if (!supabase) {
      return;
    }

    setProfileBusy(true);
    setProfileError(null);
    setProfileSchemaIssue(null);

    try {
      let { data, error, status } = await supabase
        .from("profiles")
        .select("date_of_birth, gender, boats")
        .eq("id", userId)
        .maybeSingle();

      if (error && status === 400) {
        const fallback = await supabase.from("profiles").select("*").eq("id", userId).maybeSingle();
        data = fallback.data;
        error = fallback.error;
        status = fallback.status;

        if (!error || status === 406) {
          setProfileSchemaIssue(PROFILE_MIGRATION_MESSAGE);
          setProfileError(PROFILE_MIGRATION_MESSAGE);
        }
      }

      if (error && status !== 406) {
        throw error;
      }

      const profileDobRaw = typeof data?.date_of_birth === "string"
        ? data.date_of_birth
        : typeof (data as Record<string, unknown> | null | undefined)?.dateOfBirth === "string"
          ? ((data as Record<string, unknown>).dateOfBirth as string)
          : null;
  const profileGender = normaliseGenderValue(data?.gender);
      const profileBoats = Array.isArray(data?.boats)
        ? data?.boats
            .map((item: any) => ({
              className: typeof item?.className === "string" ? item.className : "",
              sailNumber: typeof item?.sailNumber === "string" ? item.sailNumber : "",
            }))
            .filter((item) => item.className || item.sailNumber)
        : [];

  setDateOfBirth(normaliseDateForInput(profileDobRaw));
  setGender(profileGender);
      setBoats(profileBoats.length > 0 ? profileBoats.map((boat) => ({ ...boat, id: generateBoat().id })) : [generateBoat()]);
    } catch (error) {
      console.error("Failed to load profile", error);
      const message = extractSupabaseMessage(error);
      const finalMessage = message && message.toLowerCase().includes("column") ? PROFILE_MIGRATION_MESSAGE : message;
      setProfileError(finalMessage ?? "Unable to load profile data.");
      if (finalMessage === PROFILE_MIGRATION_MESSAGE) {
        setProfileSchemaIssue(PROFILE_MIGRATION_MESSAGE);
      }
    } finally {
      setProfileBusy(false);
      setProfileLoaded(true);
    }
  }, [normaliseDateForInput, supabase]);

  useEffect(() => {
    if (!supabase) {
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      if (data?.session) {
        setSession(data.session);
        fetchProfile(data.session.user.id).catch((err) => console.error(err));
      } else {
        setSession(null);
        resetProfileState();
      }
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      if (newSession) {
        fetchProfile(newSession.user.id).catch((err) => console.error(err));
      } else {
        resetProfileState();
      }
    });

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, [fetchProfile, resetProfileState, supabase]);

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthError(null);
    setAuthMessage(null);

    if (!supabase) {
      setAuthError("Supabase client is not available.");
      return;
    }

    if (!authEmail.trim() || !authPassword.trim()) {
      setAuthError("Email and password are required.");
      return;
    }

    setAuthBusy(true);
    try {
      if (authMode === "signUp") {
        const { error } = await supabase.auth.signUp({
          email: authEmail.trim(),
          password: authPassword,
          options: {
            emailRedirectTo: typeof window !== "undefined" ? `${window.location.origin}/profile` : undefined,
          },
        });
        if (error) {
          throw error;
        }
        setAuthMessage("Check your email to confirm your account before logging in.");
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: authEmail.trim(),
          password: authPassword,
        });
        if (error) {
          throw error;
        }
        setAuthMessage(null);
      }
      setAuthPassword("");
    } catch (error) {
      console.error("Auth error", error);
      const description = error instanceof Error ? error.message : "Authentication failed.";
      setAuthError(description);
    } finally {
      setAuthBusy(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setAuthError(null);
    setAuthMessage(null);

    if (!supabase) {
      setAuthError("Supabase client is not available.");
      return;
    }

    setAuthBusy(true);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: typeof window !== "undefined" ? `${window.location.origin}/profile` : undefined,
        },
      });
      if (error) {
        throw error;
      }
      setAuthMessage("Redirecting to Google…");
    } catch (error) {
      console.error("Google sign-in failed", error);
      const description = error instanceof Error ? error.message : "Google sign-in failed.";
      setAuthError(description);
    } finally {
      setAuthBusy(false);
    }
  };

  const handleSignOut = async () => {
    if (!supabase) {
      return;
    }
    setAuthError(null);
    setAuthMessage(null);
    await supabase.auth.signOut();
  };

  const handleProfileSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!supabase || !session) {
      return;
    }

    setProfileError(null);
    setProfileMessage(null);

    const cleanedBoats = boats
      .map((boat) => ({
        className: boat.className.trim(),
        sailNumber: boat.sailNumber.trim(),
      }))
      .filter((boat) => boat.className || boat.sailNumber);

    const dobValue = dateOfBirth.trim();
    let dobToPersist: string | null = null;
    if (dobValue) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dobValue)) {
        setProfileError("Date of birth must be in YYYY-MM-DD format.");
        return;
      }
      if (dobValue > todayIsoDate) {
        setProfileError("Date of birth cannot be in the future.");
        return;
      }
      dobToPersist = dobValue;
    }

    if (profileSchemaIssue) {
      setProfileError(profileSchemaIssue);
      return;
    }

    if (!gender) {
      setProfileError("Please select a gender.");
      return;
    }

    const genderToPersist = gender;

    setProfileBusy(true);
    try {
      const { error } = await supabase.from("profiles").upsert(
        {
          id: session.user.id,
          date_of_birth: dobToPersist,
          gender: genderToPersist,
          boats: cleanedBoats,
          updated_at: new Date().toISOString(),
        },
        { onConflict: "id" },
      );
      if (error) {
        throw error;
      }
      setProfileMessage("Profile saved.");
    } catch (error) {
      console.error("Profile save failed", error);
      const message = extractSupabaseMessage(error);
      const migrationMatch = message && message.toLowerCase().includes("column");
      if (migrationMatch) {
        setProfileSchemaIssue(PROFILE_MIGRATION_MESSAGE);
      }
      setProfileError(migrationMatch ? PROFILE_MIGRATION_MESSAGE : message ?? "Unable to save profile. Please try again.");
    } finally {
      setProfileBusy(false);
    }
  };

  const handleBoatChange = (boatId: string, field: keyof Omit<BoatEntry, "id">) => (event: ChangeEvent<HTMLInputElement>) => {
    const rawValue = event.target.value;
    const value = field === "className" ? normaliseBoatClassInput(rawValue) : rawValue;
    setBoats((current) => current.map((boat) => (boat.id === boatId ? { ...boat, [field]: value } : boat)));
  };

  const addBoat = () => {
    setBoats((current) => [...current, generateBoat()]);
  };

  const removeBoat = (boatId: string) => {
    setBoats((current) => (current.length <= 1 ? [generateBoat()] : current.filter((boat) => boat.id !== boatId)));
  };

  return (
    <main className={styles.container}>
      <div className={styles.stack}>
        <section className={styles.card}>
          <h2>Account access</h2>
          {configError && <div className={styles.envWarning}>{configError}</div>}
          {!session ? (
            <form className={styles.form} onSubmit={handleAuthSubmit}>
              <div className={styles.row}>
                <label className={styles.label}>
                  Email
                  <input
                    className={styles.input}
                    type="email"
                    value={authEmail}
                    onChange={(event) => setAuthEmail(event.target.value)}
                    placeholder="you@example.com"
                    disabled={authBusy || !supabase}
                    autoComplete="email"
                  />
                </label>
                <label className={styles.label}>
                  Password
                  <input
                    className={styles.input}
                    type="password"
                    value={authPassword}
                    onChange={(event) => setAuthPassword(event.target.value)}
                    placeholder="••••••••"
                    disabled={authBusy || !supabase}
                    autoComplete={authMode === "signUp" ? "new-password" : "current-password"}
                  />
                </label>
              </div>
              <div className={styles.actions}>
                <button className={styles.button} type="submit" disabled={authBusy || !supabase}>
                  {authBusy ? "Working…" : authMode === "signUp" ? "Create account" : "Sign in"}
                </button>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={() => {
                    setAuthMode((mode) => (mode === "signIn" ? "signUp" : "signIn"));
                    setAuthError(null);
                    setAuthMessage(null);
                  }}
                  disabled={authBusy}
                >
                  {authMode === "signIn" ? "Need an account?" : "Have an account?"}
                </button>
              </div>
              <button
                type="button"
                className={styles.oauthButton}
                onClick={handleGoogleSignIn}
                disabled={authBusy || !supabase}
              >
                {authBusy ? "Working…" : "Continue with Google"}
              </button>
              {authError && <p className={styles.error}>{authError}</p>}
              {authMessage && <p className={styles.muted}>{authMessage}</p>}
            </form>
          ) : (
            <div className={styles.form}>
              <p className={styles.muted}>Signed in as {session.user.email}</p>
              <div className={styles.actions}>
                <button className={styles.secondaryButton} type="button" onClick={handleSignOut}>
                  Sign out
                </button>
              </div>
            </div>
          )}
        </section>

        <section className={styles.card}>
          <h2>Your profile</h2>
          {!session && <p className={styles.muted}>Sign in to edit your profile details, including date of birth, gender, and boats.</p>}
          {session && (
            <form className={styles.form} onSubmit={handleProfileSubmit}>
              {profileSchemaIssue && <p className={styles.envWarning}>{profileSchemaIssue}</p>}
              <div className={styles.row}>
                <label className={styles.label}>
                  Date of birth
                  <input
                    className={styles.input}
                    type="date"
                    value={dateOfBirth}
                    onChange={(event) => setDateOfBirth(event.target.value)}
                    placeholder="YYYY-MM-DD"
                    disabled={profileBusy}
                    max={todayIsoDate}
                  />
                </label>
                <label className={styles.label}>
                  Gender
                  <select
                    className={styles.input}
                    value={gender}
                    onChange={(event) => setGender(normaliseGenderValue(event.target.value))}
                    disabled={profileBusy}
                  >
                    <option value="" disabled>
                      Select gender
                    </option>
                    {GENDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className={styles.divider} />

              <div className={styles.boatList}>
                <div className={clsx(styles.label, styles.muted)}>Boats</div>
                {isReferenceLoading && <p className={styles.boatHelper}>Loading PY list…</p>}
                {referenceError && (
                  <p className={clsx(styles.boatHelper, styles.boatHelperError)}>
                    Could not load the PY list. You can still type a class manually.
                  </p>
                )}
                {classOptions.length > 0 && (
                  <datalist id={BOAT_CLASS_DATALIST_ID}>
                    {classOptions.map((option) => (
                      <option key={option.key} value={option.label} />
                    ))}
                  </datalist>
                )}
                {boats.map((boat) => {
                  const trimmedClassName = boat.className.trim();
                  const canonicalClass = trimmedClassName.toUpperCase();
                  const classMatch = canonicalClass ? classLookup[canonicalClass] : undefined;

                  let helperMessage: string | null = null;
                  if (!trimmedClassName) {
                    if (isReferenceLoading) {
                      helperMessage = "Loading PY list…";
                    } else if (referenceError) {
                      helperMessage = "Enter a boat class (PY list unavailable).";
                    } else if (classOptions.length > 0) {
                      helperMessage = "Start typing to search the PY list.";
                    }
                  } else if (classMatch) {
                    helperMessage = classMatch.py != null ? `PY ${classMatch.py}` : "Listed in PY data";
                  } else if (!isReferenceLoading && !referenceError) {
                    helperMessage = "Not found in PY list";
                  }

                  const helperClassName = clsx(styles.boatHelper, {
                    [styles.boatHelperError]:
                      !!trimmedClassName && !classMatch && !isReferenceLoading && !referenceError,
                  });

                  return (
                    <div key={boat.id} className={styles.boatRow}>
                      <div className={styles.boatField}>
                        <input
                          className={styles.input}
                          value={boat.className}
                          onChange={handleBoatChange(boat.id, "className")}
                          placeholder="Boat class (e.g. Laser)"
                          disabled={profileBusy}
                          list={classOptions.length > 0 ? BOAT_CLASS_DATALIST_ID : undefined}
                        />
                        {helperMessage && <p className={helperClassName}>{helperMessage}</p>}
                      </div>
                      <div className={styles.boatField}>
                        <input
                          className={styles.input}
                          value={boat.sailNumber}
                          onChange={handleBoatChange(boat.id, "sailNumber")}
                          placeholder="Sail number"
                          disabled={profileBusy}
                        />
                      </div>
                      <button
                        type="button"
                        className={styles.boatRemove}
                        onClick={() => removeBoat(boat.id)}
                        disabled={profileBusy}
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}
                <button type="button" className={styles.secondaryButton} onClick={addBoat} disabled={profileBusy}>
                  Add another boat
                </button>
              </div>

              <div className={styles.actions}>
                <button
                  className={styles.button}
                  type="submit"
                  disabled={profileBusy || !profileLoaded || !!profileSchemaIssue}
                >
                  {profileBusy ? "Saving…" : "Save profile"}
                </button>
              </div>
              {profileError && <p className={styles.error}>{profileError}</p>}
              {profileMessage && <p className={styles.success}>{profileMessage}</p>}
            </form>
          )}
        </section>
      </div>
    </main>
  );
}
