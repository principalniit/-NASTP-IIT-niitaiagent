"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Accessible tabs (WAI-ARIA tabs pattern): arrow keys, Home and End move between tabs,
 * only the selected tab is in the tab order, and only the selected panel is rendered.
 */
interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
  baseId: string;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs(): TabsContextValue {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("Tabs parts must be used inside <Tabs>");
  return context;
}

const safe = (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, "-");

export function Tabs({
  defaultValue,
  value: controlled,
  onValueChange,
  className,
  children,
}: {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultValue ?? "");
  const value = controlled ?? uncontrolled;
  const baseId = React.useId();
  const setValue = React.useCallback(
    (next: string) => {
      if (controlled === undefined) setUncontrolled(next);
      onValueChange?.(next);
    },
    [controlled, onValueChange],
  );
  return (
    <TabsContext.Provider value={{ value, setValue, baseId }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, label, children }: { className?: string; label: string; children: React.ReactNode }) {
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])'));
    const index = tabs.indexOf(document.activeElement as HTMLButtonElement);
    if (index < 0) return;
    const target =
      event.key === "ArrowRight"
        ? tabs[(index + 1) % tabs.length]
        : event.key === "ArrowLeft"
          ? tabs[(index - 1 + tabs.length) % tabs.length]
          : event.key === "Home"
            ? tabs[0]
            : event.key === "End"
              ? tabs[tabs.length - 1]
              : null;
    if (!target) return;
    event.preventDefault();
    target.focus();
    target.click();
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn(
        "inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl border bg-muted/60 p-1 text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  className,
  children,
  disabled,
}: {
  value: string;
  className?: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  const tabs = useTabs();
  const selected = tabs.value === value;
  return (
    <button
      type="button"
      role="tab"
      id={`${tabs.baseId}-tab-${safe(value)}`}
      aria-selected={selected}
      aria-controls={`${tabs.baseId}-panel-${safe(value)}`}
      tabIndex={selected ? 0 : -1}
      disabled={disabled}
      onClick={() => tabs.setValue(value)}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-all",
        "hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        "[&_svg]:size-4 [&_svg]:shrink-0",
        selected && "bg-card text-foreground shadow-sm",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, className, children }: { value: string; className?: string; children: React.ReactNode }) {
  const tabs = useTabs();
  if (tabs.value !== value) return null;
  return (
    <div
      role="tabpanel"
      id={`${tabs.baseId}-panel-${safe(value)}`}
      aria-labelledby={`${tabs.baseId}-tab-${safe(value)}`}
      tabIndex={0}
      className={cn("mt-4 animate-fade-up focus-visible:outline-none", className)}
    >
      {children}
    </div>
  );
}
