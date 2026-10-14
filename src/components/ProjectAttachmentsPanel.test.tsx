import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { ProjectAttachment } from "../types";
import { ProjectAttachmentsPanel } from "./ProjectAttachmentsPanel";

vi.mock("../api/client", () => ({
  api: {
    attachments: {
      list: vi.fn(),
      upload: vi.fn(),
      scan: vi.fn(),
      remove: vi.fn(),
      download: vi.fn(),
    },
  },
}));

const cleanAttachment: ProjectAttachment = {
  id: "clean-attachment",
  project_id: "project-1",
  name: "brief.txt",
  mime: "text/plain",
  size_bytes: 12,
  status: "clean",
  created_at: "2026-10-13T12:00:00Z",
  scanned_at: "2026-10-13T12:01:00Z",
};

const quarantinedAttachment: ProjectAttachment = {
  ...cleanAttachment,
  id: "quarantined-attachment",
  name: "pending.txt",
  status: "quarantined",
  scanned_at: null,
};

function renderPanel(onSelectedIdsChange = vi.fn()) {
  return render(
    <ProjectAttachmentsPanel
      projectId="project-1"
      selectedIds={[]}
      onSelectedIdsChange={onSelectedIdsChange}
    />,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("ProjectAttachmentsPanel", () => {
  it("allows only clean-scanned files to be selected for a run", async () => {
    vi.mocked(api.attachments.list).mockResolvedValue({
      items: [cleanAttachment, quarantinedAttachment],
      next_cursor: null,
    });
    const onSelectedIdsChange = vi.fn();
    renderPanel(onSelectedIdsChange);

    fireEvent.click(screen.getByRole("button", { name: /files/i }));

    const cleanCheckbox = await screen.findByRole("checkbox", {
      name: "Attach brief.txt to the next run",
    });
    const quarantinedCheckbox = screen.getByRole("checkbox", {
      name: "Attach pending.txt to the next run",
    });

    expect(cleanCheckbox).not.toBeDisabled();
    expect(quarantinedCheckbox).toBeDisabled();
    fireEvent.click(cleanCheckbox);
    expect(onSelectedIdsChange).toHaveBeenCalledWith(["clean-attachment"]);
  });

  it("automatically selects a clean-scanned upload for the next task", async () => {
    vi.mocked(api.attachments.list)
      .mockResolvedValueOnce({ items: [], next_cursor: null })
      .mockResolvedValueOnce({ items: [cleanAttachment], next_cursor: null });
    vi.mocked(api.attachments.upload).mockResolvedValue(cleanAttachment);
    function ControlledPanel() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      return (
        <ProjectAttachmentsPanel
          projectId="project-1"
          selectedIds={selectedIds}
          onSelectedIdsChange={setSelectedIds}
        />
      );
    }
    render(<ControlledPanel />);

    fireEvent.click(screen.getByRole("button", { name: /files/i }));
    // The file control is visually hidden but remains label-accessible.
    const fileInput = screen.getByLabelText("Choose project files to upload") as HTMLInputElement;

    const file = new File(["Project brief"], "brief.txt", { type: "text/plain" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(await screen.findByText("brief.txt")).toBeTruthy();
    expect(api.attachments.upload).toHaveBeenCalledWith("project-1", file);
    expect(screen.getByRole("checkbox", { name: "Attach brief.txt to the next run" })).toBeChecked();
  });
});
