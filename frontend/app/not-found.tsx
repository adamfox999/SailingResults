import Link from "next/link";
import styles from "./page.module.css";

export default function NotFound() {
  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        <h1>Page not found</h1>
  <p>The page you&rsquo;re looking for doesn&rsquo;t exist. Try one of the primary actions below.</p>
        <div className={styles.headerLinks}>
          <Link href="/" className={styles.linkButton}>
            Score a race
          </Link>
          <Link href="/portal" className={styles.linkButton}>
            Race day portal
          </Link>
          <Link href="/standings" className={styles.linkButton}>
            View standings
          </Link>
        </div>
      </div>
    </main>
  );
}
