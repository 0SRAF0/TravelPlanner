// Minimal JSX and runtime declarations to silence editor/TS server errors when @types/react isn't picked up by the environment.
// Prefer removing this file and installing @types/react/@types/react-dom in your project if possible.

declare global {
  namespace JSX {
    // allow any intrinsic element (e.g., <div>, <button>)
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

// Provide a tiny module declaration for the automatic JSX runtime path
declare module "react/jsx-runtime" {
  export function jsx(type: any, props: any, key?: any): any;
  export function jsxs(type: any, props: any, key?: any): any;
  export function jsxDEV(type: any, props: any, key?: any): any;
  export const Fragment: any;
}

export {};

