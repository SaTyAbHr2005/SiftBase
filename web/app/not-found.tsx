import Link from "next/link";

export default function NotFound() {
  return (
    <main className="lost">
      {/* eslint-disable-next-line @next/next/no-img-element -- pre-sized WebP; next/image would add Vercel's metered optimiser */}
      <img className="lost-photo" src="/assets/stream/pool.webp" alt="" width={1376} height={768} />
      <div className="stone lost-note">
        <h1 className="h2">This page washed downstream.</h1>
        <p className="lede">No page sits at this address. The link may be old, or the address has a typo.</p>
        <Link className="nugget" href="/">Back to the falls</Link>
      </div>
    </main>
  );
}
