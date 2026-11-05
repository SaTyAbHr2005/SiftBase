import Link from "next/link";

export default function NotFound() {
  return (
    <main className="lost">
      <div className="empty-pan" aria-hidden="true">
        <span className="pyrite-flake" />
      </div>
      <div className="stone stone--b lost-note">
        <h1 className="h2">Nothing panned here.</h1>
        <p className="lede">No page sits at this address. The link may be old, or the address has a typo.</p>
        <Link className="nugget" href="/">Back to the pan</Link>
      </div>
    </main>
  );
}
