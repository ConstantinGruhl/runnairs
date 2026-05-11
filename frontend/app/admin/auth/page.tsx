"use client";

import { OidcProviderForm } from "@/components/OidcProviderForm";

export default function AdminAuthPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Authentication</h1>
        <p className="text-sm text-muted-foreground">
          Configure built-in IAM and the OpenID Connect provider used for single sign-on. OIDC is configured
          here after first-run setup; the bootstrap admin always keeps a built-in password as a break-glass
          account.
        </p>
      </div>
      <OidcProviderForm />
    </div>
  );
}
