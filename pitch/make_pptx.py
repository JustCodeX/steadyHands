"""Build steady-hands-pitch.pptx from index.html, with the demo video embedded.

Each slide is rendered by headless Chrome at twice the size and placed as a
full-slide picture, so the deck looks exactly like the HTML. The video slide
gets media/demo.mp4 as a real PowerPoint video on top of its frame, set to
start by itself. The speaker notes are copied into PowerPoint's notes.

    pip install python-pptx lxml
    python make_pptx.py            # from pitch/

The text on the slides is part of the pictures: change index.html and run this
again rather than editing the deck.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.util import Emu

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = HERE / "steady-hands-pitch.pptx"
VIDEO = HERE / "media" / "demo.mp4"
POSTER = HERE / "media" / "demo-poster.jpg"
STAGE_W, STAGE_H = 1600, 900
SLIDE_W, SLIDE_H = 12192000, 6858000  # 13.333 x 7.5 in, 16:9
PX = SLIDE_W // STAGE_W  # EMU per stage pixel
# The video's place inside .video-frame (index.html, slide 4 CSS): the frame is
# 1300 x 744 at top 76, centred, with 14 px of padding.
VIDEO_BOX = ((STAGE_W - 1300) // 2 + 14, 76 + 14, 1300 - 28, 744 - 28)

NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def slides_and_notes(page: str) -> list[tuple[bool, str, str]]:
    """(is the video slide, title, speaker notes) for each <section class="slide">."""
    out = []
    for sec in re.findall(r'<section class="slide.*?</section>', page, re.S):
        m = re.search(r'<div class="speaker-notes">(.*?)</div>', sec, re.S)
        notes = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
        t = re.search(r"<h1[^>]*>(.*?)</h1>", sec, re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else "Demo video"
        out.append(('data-video="yes"' in sec, title, notes))
    return out


def render(n: int, folder: Path) -> Path:
    shot = folder / f"slide{n}.png"
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
         f"--window-size={STAGE_W},{STAGE_H}", "--force-device-scale-factor=2",
         "--virtual-time-budget=3000", f"--user-data-dir={folder / 'chrome'}",
         f"--screenshot={shot}", f"{(HERE / 'index.html').as_uri()}#{n}"],
        check=True, capture_output=True,
    )
    return shot


def autoplay(slide, spid: int) -> None:
    """Replace the click-to-play timing with PowerPoint's 'Start: Automatically'."""
    xml = f"""
<p:timing xmlns:p="{NS}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>
  <p:par><p:cTn id="2" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>
    <p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>
      <p:par><p:cTn id="4" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="afterEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>
        <p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr><p:cTn id="5" dur="45000" fill="hold"/><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:cmd>
      </p:childTnLst></p:cTn></p:par>
    </p:childTnLst></p:cTn></p:par>
  </p:childTnLst></p:cTn></p:par>
  <p:video><p:cMediaNode vol="80000"><p:cTn id="6" fill="hold" display="0"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cMediaNode></p:video>
</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>"""
    sld = slide._element
    for old in sld.findall(f"{{{NS}}}timing"):
        sld.remove(old)
    timing = etree.fromstring(xml.strip())
    # p:sld children run cSld, clrMapOvr, transition, timing, extLst
    ext = sld.find(f"{{{NS}}}extLst")
    if ext is not None:
        ext.addprevious(timing)
    else:
        sld.append(timing)


def main() -> None:
    page = (HERE / "index.html").read_text(encoding="utf-8")
    slides = slides_and_notes(page)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(SLIDE_W), Emu(SLIDE_H)
    blank = prs.slide_layouts[6]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for n, (is_video, title, notes) in enumerate(slides, 1):
            slide = prs.slides.add_slide(blank)
            pic = slide.shapes.add_picture(str(render(n, folder)), 0, 0, Emu(SLIDE_W), Emu(SLIDE_H))
            pic.name = f"Slide {n}"
            pic._element.nvPicPr.cNvPr.set("descr", f"Slide {n}: {title}")
            if is_video:
                x, y, w, h = (v * PX for v in VIDEO_BOX)
                movie = slide.shapes.add_movie(str(VIDEO), Emu(x), Emu(y), Emu(w), Emu(h),
                                               poster_frame_image=str(POSTER), mime_type="video/mp4")
                movie.name = "Demo video"
                autoplay(slide, movie.shape_id)
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
            print(f"slide {n}{' + video' if is_video else ''}")
    prs.save(OUT)
    print(f"saved {OUT.name} ({OUT.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    sys.exit(main())
