# Background pictures

Drop your image here (JPG/WebP, ideally under 300 KB, 1920px wide), then point a CSS variable at it in
`src/shared/styles/base.css`:

```css
:root {
  --bg-image: url("/backdrop/app.jpg");        /* signed-in workspace */
  --bg-image-land: url("/backdrop/landing.jpg"); /* landing page */
  --bg-image-opacity: 0.35;                    /* optional: soften it so text stays readable */
}
```

Leave both as `none` and the pages stay one flat colour. Cards are opaque, so text remains readable over any picture.
Rebuild with `npm run build` (the built files in `frontend/dist` are what the server and Vercel serve).
