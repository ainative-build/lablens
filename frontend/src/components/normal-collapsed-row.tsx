"use client";

import { useState } from "react";
import type { Explanation, InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { AnalyteCard } from "./analyte-card";
import { Disclosure } from "./disclosure";

interface Props {
  values: InterpretedValue[];
  explanations: Explanation[];
  language: Language;
}

/** Single-line minimized row that expands to show normal results. */
export function NormalCollapsedRow({ values, explanations, language }: Props) {
  const [open, setOpen] = useState(false);
  if (values.length === 0) return null;
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-2 mt-2">
      <Disclosure
        isOpen={open}
        onToggle={() => setOpen((v) => !v)}
        triggerClassName="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 inline-flex items-center gap-1"
        bodyClassName="mt-2 space-y-2"
        trigger={
          <>
            <span aria-hidden>{open ? "▾" : "▸"}</span>
            {t("group.normal_collapsed", language, { count: values.length })}
          </>
        }
      >
        {values.map((v, i) => {
          const exp = explanations.find((e) => e.test_name === v.test_name);
          return (
            <AnalyteCard
              key={`${v.test_name}-${i}`}
              value={v}
              explanation={exp}
              language={language}
            />
          );
        })}
      </Disclosure>
    </div>
  );
}
