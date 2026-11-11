import { PageHeader } from "../components/Layout";

export function PlaceholderPage({ title, availableIn, description }: { title: string; availableIn: string; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="rounded-lg border border-dashed border-hairline bg-surface p-8 text-sm text-ink-secondary">
        <p className="font-medium text-ink">Planned for {availableIn}</p>
        <p className="mt-1 max-w-2xl">{description}</p>
      </div>
    </>
  );
}
