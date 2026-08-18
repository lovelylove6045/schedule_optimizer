const PAGE_MARGIN_MM = 8
const CAPTURE_PIXEL_RATIO = 1.5

/** Download a rendered plan board as a paginated PDF without changing its visual design. */
export async function downloadPlanPdf(element: HTMLElement, filename: string): Promise<void> {
  const [{ toCanvas }, { jsPDF }] = await Promise.all([import("html-to-image"), import("jspdf")])
  element.classList.add("pdf-exporting")
  try {
    await document.fonts?.ready
    await waitForPaint()
    const sectionOffsets = pdfSectionOffsets(element)
    const canvas = await toCanvas(element, {
      backgroundColor: "#f5f8fc",
      cacheBust: true,
      height: element.scrollHeight,
      pixelRatio: CAPTURE_PIXEL_RATIO,
      width: element.scrollWidth,
    })
    const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true })
    pdf.setProperties({ title: filename.replace(/\.pdf$/i, ""), subject: "Optimized degree schedule" })
    const sectionBreaks = sectionOffsets.map((offset) => Math.round(offset * canvas.height / element.scrollHeight))
    addCanvasPages(pdf, canvas, sectionBreaks)
    pdf.save(safePdfFilename(filename))
  } finally {
    element.classList.remove("pdf-exporting")
  }
}

/** Return section-bottom offsets used to keep academic-year cards on one page when possible. */
function pdfSectionOffsets(element: HTMLElement): number[] {
  const rootTop = element.getBoundingClientRect().top
  return Array.from(element.querySelectorAll<HTMLElement>("[data-pdf-section]"))
    .map((section) => section.getBoundingClientRect().bottom - rootTop)
    .filter((offset) => offset > 0)
    .sort((a, b) => a - b)
}

/** Yield one animation frame so export-only visibility styles reach layout and paint. */
function waitForPaint(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()))
}

/** Add successive canvas slices to portrait A4 pages without stretching their aspect ratio. */
function addCanvasPages(pdf: InstanceType<typeof import("jspdf").jsPDF>, canvas: HTMLCanvasElement, sectionBreaks: number[]): void {
  const pageWidth = pdf.internal.pageSize.getWidth()
  const pageHeight = pdf.internal.pageSize.getHeight()
  const contentWidth = pageWidth - 2 * PAGE_MARGIN_MM
  const contentHeight = pageHeight - 2 * PAGE_MARGIN_MM
  const millimetersPerPixel = contentWidth / canvas.width
  const sourcePageHeight = Math.max(1, Math.floor(contentHeight / millimetersPerPixel))
  let sourceY = 0
  let pageIndex = 0
  while (sourceY < canvas.height) {
    const sliceHeight = nextSliceHeight(sourceY, sourcePageHeight, canvas.height, sectionBreaks)
    if (pageIndex > 0) pdf.addPage()
    addCanvasSlice(pdf, canvas, sourceY, sliceHeight, contentWidth, millimetersPerPixel)
    sourceY += sliceHeight
    pageIndex += 1
  }
}

/** Prefer the last useful section boundary on a page, falling back to a full page slice. */
function nextSliceHeight(sourceY: number, maximumHeight: number, canvasHeight: number, sectionBreaks: number[]): number {
  const target = Math.min(sourceY + maximumHeight, canvasHeight)
  const minimumUsefulBreak = sourceY + Math.floor(maximumHeight * 0.2)
  const candidates = sectionBreaks.filter((offset) => offset > minimumUsefulBreak && offset <= target)
  const breakAt = candidates.at(-1) ?? target
  return Math.max(1, breakAt - sourceY)
}

/** Draw one source-canvas band onto the current PDF page. */
function addCanvasSlice(
  pdf: InstanceType<typeof import("jspdf").jsPDF>,
  source: HTMLCanvasElement,
  sourceY: number,
  sliceHeight: number,
  contentWidth: number,
  millimetersPerPixel: number,
): void {
  const slice = document.createElement("canvas")
  slice.width = source.width
  slice.height = sliceHeight
  const context = slice.getContext("2d")
  if (!context) throw new Error("The browser could not prepare the PDF image.")
  context.fillStyle = "#f5f8fc"
  context.fillRect(0, 0, slice.width, slice.height)
  context.drawImage(source, 0, sourceY, source.width, sliceHeight, 0, 0, source.width, sliceHeight)
  const image = slice.toDataURL("image/jpeg", 0.94)
  pdf.addImage(image, "JPEG", PAGE_MARGIN_MM, PAGE_MARGIN_MM, contentWidth, sliceHeight * millimetersPerPixel, undefined, "FAST")
}

/** Return a filesystem-safe PDF filename while preserving a readable plan label. */
function safePdfFilename(filename: string): string {
  const base = filename.replace(/\.pdf$/i, "").replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "")
  return `${base || "degree-plan"}.pdf`
}
