// Data access. The default source is the static JSON the judge publishes (public/data/…).
// Set VITE_DATA_SOURCE=firestore plus VITE_FIREBASE_* to read the same documents from Firestore
// (written by `judge run --store firestore`), which also lets the page update without a rebuild.
import { useEffect, useState } from "react";
import type { ResultsIndex, Submission } from "./types";

const source = import.meta.env.VITE_DATA_SOURCE ?? "static";

async function firestoreDb() {
  const [{ initializeApp, getApps }, fs] = await Promise.all([import("firebase/app"), import("firebase/firestore")]);
  const app = getApps()[0] ?? initializeApp({
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  });
  return { db: fs.getFirestore(app), fs };
}

async function loadIndex(): Promise<ResultsIndex> {
  if (source === "firestore") {
    const { db, fs } = await firestoreDb();
    const snap = await fs.getDoc(fs.doc(db, "meta", "index"));
    if (!snap.exists()) throw new Error("meta/index not found in Firestore");
    return snap.data() as ResultsIndex;
  }
  const res = await fetch("data/results.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`results.json: HTTP ${res.status}`);
  return res.json();
}

async function loadSubmission(id: string): Promise<Submission> {
  if (!/^[\w.-]+$/.test(id)) throw new Error("invalid submission id");
  if (source === "firestore") {
    const { db, fs } = await firestoreDb();
    const snap = await fs.getDoc(fs.doc(db, "details", id));
    if (!snap.exists()) throw new Error(`details/${id} not found`);
    return snap.data() as Submission;
  }
  const res = await fetch(`data/pr/${id}.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Submission ${id} not found`);
  return res.json();
}

type State<T> = { data: T | null; error: string | null; loading: boolean };

function useAsync<T>(fn: () => Promise<T>, key: string): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    // Keep the previous render visible while refetching (no skeleton flash).
    setState((s) => ({ ...s, loading: true }));
    fn().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e: unknown) => live && setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

let indexPromise: Promise<ResultsIndex> | null = null;
const cachedIndex = () => (indexPromise ??= loadIndex().catch((e) => ((indexPromise = null), Promise.reject(e))));

export const useIndex = () => useAsync(cachedIndex, "index");
export const useSubmission = (id: string) => useAsync(() => loadSubmission(id), id);
