"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { clsx } from "clsx";
import styles from "./layout.module.css";

const NAV_LINKS = [
  { href: "/admin/races", label: "Scheduled races" },
  { href: "/admin/series", label: "Series" },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className={styles.wrapper}>
      <header className={styles.header}>
        <div>
          <h1>Race administration</h1>
          <p className={styles.tagline}>Plan the season calendar and keep metadata ready for race day.</p>
        </div>
        <Link href="/" className={styles.backLink}>
          ← Back to scoring
        </Link>
      </header>

      <nav className={styles.nav}>
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={clsx(styles.navLink, pathname === link.href && styles.activeNavLink)}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className={styles.content}>{children}</div>
    </div>
  );
}
