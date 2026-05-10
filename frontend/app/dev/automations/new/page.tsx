"use client";

import { AutomationScaffoldForm } from "@/components/AutomationScaffoldForm";

export default function NewAutomationPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New automation</h1>
        <p className="text-sm text-muted-foreground">
          Start with a native `automation.yaml` package and fill in the business logic afterward.
        </p>
      </div>
      <AutomationScaffoldForm />
    </div>
  );
}
