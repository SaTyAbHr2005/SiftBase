"use client";

// Lenis smooth scrolling driven by GSAP's ticker, so ScrollTrigger and the scroll stay in step.
// Off with reduced motion; anchor links scroll through Lenis.
import { useEffect } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function SmoothScroll() {
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ autoRaf: false, anchors: true, lerp: 0.11 });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (t: number) => lenis.raf(t * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => { gsap.ticker.remove(tick); gsap.ticker.lagSmoothing(500, 33); lenis.destroy(); };
  }, []);
  return null;
}
