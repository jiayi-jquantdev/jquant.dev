"use client";
import { useState } from "react";
import Link from "next/link";

export default function MobileSidebar() {
  const [visible, setVisible] = useState(false);
  const [active, setActive] = useState(false);
  function openMenu() {
    setVisible(true);
    // allow element to mount then trigger CSS transition
    setTimeout(() => setActive(true), 16);
  }
  function closeMenu() {
    setActive(false);
    // wait for animation to finish then unmount
    setTimeout(() => setVisible(false), 300);
  }
  return (
    <>
      <button aria-label="Open menu" onClick={openMenu} className="sm:hidden p-2">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      {visible && (
        <div className={`mobile-drawer fixed inset-0 z-50 flex ${active ? 'open' : ''}`}>
          <div className={`drawer-panel w-72 bg-background p-4 shadow-lg`}>
            <div className="flex items-center justify-between mb-4">
              <div className="font-semibold">Menu</div>
              <button onClick={closeMenu} aria-label="Close menu" className="p-2">
                ✕
              </button>
            </div>
            <nav className="flex flex-col gap-3">
              <a href="https://instagram.com/jquant.dev" target="_blank" rel="noopener noreferrer" className="underline">@jquant.dev</a>
              <a href="https://instagram.com/jiayi.jquant" target="_blank" rel="noopener noreferrer" className="underline">@jiayi.jquant</a>
              <a href="mailto:jiayi@jquant.dev" target="_blank" rel="noopener noreferrer" className="underline">jiayi@jquant.dev</a>
              <Link href="/terms" className="underline">Terms</Link>
              <Link href="/privacy" className="underline">Privacy</Link>
              <Link href="/legal" className="underline">Legal</Link>
            </nav>
          </div>
          <div className="drawer-backdrop flex-1" onClick={closeMenu} />
        </div>
      )}
    </>
  );
}
