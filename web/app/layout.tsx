import type { Metadata, Viewport } from "next";
import { Big_Shoulders, Bricolage_Grotesque, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const grotesque = Bricolage_Grotesque({ variable: "--font-grotesque", subsets: ["latin"], axes: ["wdth", "opsz"] });
const shoulders = Big_Shoulders({ variable: "--font-figures", subsets: ["latin"], weight: ["700", "800"] });
const serif = Source_Serif_4({ variable: "--font-serif", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SiftBase: 6,970 pages go in, only the gold comes out",
  description:
    "A knowledge base for AI agents that checks every claim against the exact source text and cites document and page. Runs on free model tiers, with its measured scores published.",
};

export const viewport: Viewport = { themeColor: "#0B1A12", colorScheme: "dark" };

// Runs before first paint: turns on the scroll-scrubbed stream only where it can play
// (motion allowed, WebGL2 available). Everyone else gets the still photographs from the start.
const SCENE_CHECK = `try{var g=!matchMedia("(prefers-reduced-motion: reduce)").matches&&document.createElement("canvas").getContext("webgl2",{failIfMajorPerformanceCaveat:true});if(g){document.documentElement.classList.add("has-scene");var x=g.getExtension("WEBGL_lose_context");x&&x.loseContext()}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${grotesque.variable} ${shoulders.variable} ${serif.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCENE_CHECK }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
