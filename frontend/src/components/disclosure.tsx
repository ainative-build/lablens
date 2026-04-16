"use client";

import { useId } from "react";
import type { ReactNode } from "react";

interface Props {
  isOpen: boolean;
  onToggle: () => void;
  trigger: ReactNode;
  children: ReactNode;
  triggerClassName?: string;
  bodyClassName?: string;
  ariaLabel?: string;
}

/**
 * Generic expand/collapse primitive used across L2 (topic group), L3 (analyte
 * card audit), L4 (audit panel), and the normal-collapsed-row pattern.
 *
 * a11y:
 *  - <button aria-expanded aria-controls> trigger
 *  - body has matching id
 *  - keyboard: Enter/Space toggles; arrow nav handled by parent group container
 */
export function Disclosure({
  isOpen,
  onToggle,
  trigger,
  children,
  triggerClassName = "",
  bodyClassName = "",
  ariaLabel,
}: Props) {
  const id = useId();
  return (
    <>
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={id}
        aria-label={ariaLabel}
        onClick={onToggle}
        className={`text-left w-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ${triggerClassName}`}
      >
        {trigger}
      </button>
      {isOpen && (
        <div id={id} className={bodyClassName}>
          {children}
        </div>
      )}
    </>
  );
}
