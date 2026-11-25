# Transcribed from video_2026-11-25_11-41-12.mp4, source lines 259-337.
# Fragment only: imports, Renderer class, settings and frame source are outside the video.

def convert(self, frame: np.ndarray):
    s, cols, rows = self.s, self.cols, self.rows
    use_blocks = s.mode == "blocks" and s.color
    img = cv2.resize(frame, (cols, rows * 2 if use_blocks else rows),
                    interpolation=cv2.INTER_AREA)
    img = cv2.LUT(img, self.lut)
    if s.saturation != 1.0 and s.color:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * s.saturation, 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    rgb = img[..., ::-1].astype(np.float32)

    if use_blocks:
        glyph = np.full((rows, cols), "▀", dtype="<U1")
        return glyph, self._pack(rgb[0::2]), self._pack(rgb[1::2])

    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0
    n = len(self.ramp)
    idx = np.clip((lum * (n - 1) + 0.5).astype(np.int32), 0, n - 1)
    idx[lum < 0.06] = 0
    glyph = self.ramp[idx]

    if s.edges > 0:
        gray = lum.astype(np.float32)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.hypot(gx, gy) / 4.0
        ang = (np.degrees(np.arctan2(gy, gx)) + 90.0) % 180.0
        sel = np.array(["-", "\\", "|", "/"])[(((ang + 22.5) % 180.0) //
                 45).astype(np.int32)]
        mask = (mag > (0.8 - 0.6 * s.edges)) & (lum > 0.12)
        glyph = np.where(mask, sel, glyph)

    if not s.color:
        neg = np.full(glyph.shape, -1, dtype=np.int32)
        return glyph, neg, neg

    v = np.maximum(rgb.max(-1, keepdims=True), 1.0)
    fg_rgb = rgb * 0.4 + rgb * (255.0 / v) * 0.6
    fg = self._pack(fg_rgb)
    bg = self._pack(rgb * s.bg_tint)
    blank = glyph == " "
    fg = np.where(blank, 0, fg)
    return glyph, fg, bg


def draw(self, grid) -> int:
    glyph, fg, bg = grid
    out: list[str] = []
    pg = self.prev
    for y in range(self.rows):
        if pg is None:
            idxs = np.arange(self.cols)
        else:
            ch = (glyph[y] != pg[0][y]) | (fg[y] != pg[1][y]) | (bg[y] != pg[2][y])
            idxs = np.flatnonzero(ch)
            if idxs.size == 0:
                continue

        seg_start = prev_i = int(idxs[0])
        segs = []
        for i in idxs[1:]:
            i = int(i)
            if i - prev_i > 6:
                segs.append((seg_start, prev_i)); seg_start = i
            prev_i = i
        segs.append((seg_start, prev_i))
        for a, b in segs:
            out.append(f"\x1b[{self.y0 + y + 1};{self.x0 + a + 1}H")
            for x in range(a, b + 1):
                f, k = int(fg[y, x]), int(bg[y, x])
                if k != self.cur_bg:
                    out.append(self._sgr("b", k)); self.cur_bg = k
                if f != self.cur_fg:
                    out.append(self._sgr("f", f)); self.cur_fg = f
                out.append(glyph[y, x])
    self.prev = (glyph.copy(), fg.copy(), bg.copy())
    text = "".join(out)
    if text:
        self.term.write(text)
    return len(text)
