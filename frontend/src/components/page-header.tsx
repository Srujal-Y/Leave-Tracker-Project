"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageHeaderProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  badge?: ReactNode;
  className?: string;
};

export function PageHeader({ title, description, actions, badge, className }: PageHeaderProps) {
  return (
    <section className={cn("page-head", className)}>
      <div className="min-w-0">
        <div className="mb-2">{badge}</div>
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-subtitle">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </section>
  );
}
