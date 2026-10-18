(() => {
  const visualBlockTextColors = [
    "#c62828",
    "#2e7d32",
    "#1565c0",
    "#6a1b9a",
    "#ad1457",
    "#ef6c00",
    "#9a7d00",
  ];

  const closestBeat = (node) => {
    const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    return element?.closest("[data-narration-target]");
  };

  const rangeOffset = (container, node, offset) => {
    const range = document.createRange();
    range.selectNodeContents(container);
    range.setEnd(node, offset);
    return range.toString().length;
  };

  document.querySelectorAll(".format-package-editor").forEach((editor) => {
    const scriptDocument = editor.querySelector("[data-script-document]");
    const scriptBody = editor.querySelector("[data-script-document-body]");
    const focus = editor.querySelector(".format-script-focus");
    const threadLayer = editor.querySelector("[data-comment-thread-layer]");
    const selectionForm = editor.querySelector("[data-selection-comment-form]");
    const selectionInput = selectionForm?.elements.namedItem("comment_text");
    const generalCommentInput = editor.querySelector("[data-general-comment-input]");
    const visualTimeline = editor.querySelector("[data-visual-timeline]");
    const commentsDisabled = editor.dataset.commentsDisabled === "true";
    const editingDisabled = editor.dataset.editingDisabled === "true";
    const scriptEditor = editor.querySelector("[data-script-editor]");
    const saveStatus = editor.querySelector("[data-package-save-status]");
    const titleCarousel = editor.querySelector("[data-title-carousel]");
    const titleEditor = titleCarousel?.querySelector("[data-title-editor]");
    const titleOptions = [
      ...(titleCarousel?.querySelectorAll("[data-title-option]") || []),
    ];
    const titlePosition = titleCarousel?.querySelector("[data-title-position]");
    const titleSelected = titleCarousel?.querySelector("[data-title-selected]");
    const titleSelect = titleCarousel?.querySelector("[data-title-select]");
    let titleIndex = 0;
    let saveTimer;
    let saving = false;
    let editRevision = 0;
    let pendingSelection = null;
    let fallbackHighlights = [];
    let scriptPagesManuallySelected = false;
    let activeVisualSource = null;

    const showSaveState = (state, message) => {
      editor.dataset.autosaveState = state;
      if (saveStatus) saveStatus.textContent = message;
    };

    const editableText = (element) => element?.textContent || "";

    const titles = () => titleOptions.map((option) => option.value);

    const updateTitleOutputs = (title) => {
      const selector = document.querySelector(
        `[data-script-selector-link="${CSS.escape(titleCarousel?.dataset.packageId || "")}"]`,
      );
      const selectorLabel = selector?.querySelector(".format-script-selector-label");
      if (selectorLabel) {
        const words = title.trim().split(/\s+/).filter(Boolean);
        selectorLabel.textContent = `${words.slice(0, 6).join(" ")}${words.length > 6 ? "…" : ""}`;
        selector.title = title;
      }
      const exportTitle = editor.querySelector("[data-copy-export-source] p");
      if (exportTitle) exportTitle.textContent = title;
      const plain = editor.querySelector("[data-copy-export-plain]");
      if (plain) {
        const lines = plain.value.split("\n");
        lines[0] = title;
        plain.value = lines.join("\n");
      }
    };

    const renderTitle = () => {
      if (!titleEditor || !titleOptions.length) return;
      if (!titleEditor.matches(":focus")) titleEditor.textContent = titleOptions[titleIndex].value;
      if (titlePosition) titlePosition.textContent = `${titleIndex + 1} / ${titleOptions.length}`;
      if (titleSelected) titleSelected.hidden = titleIndex !== 0;
      if (titleSelect) titleSelect.hidden = titleIndex === 0;
      updateTitleOutputs(titleOptions[0].value);
    };

    const selectTitle = (index) => {
      if (editingDisabled || index === 0) return;
      const ranked = titles();
      const [selected] = ranked.splice(index, 1);
      ranked.unshift(selected);
      titleOptions.forEach((option, optionIndex) => {
        option.value = ranked[optionIndex];
      });
      titleIndex = 0;
      renderTitle();
      queueSave();
    };

    const collectVisualEdits = () => [
      ...editor.querySelectorAll("[data-visual-description-editor][data-visual-id]"),
    ].map((description) => {
      const id = description.dataset.visualId;
      const action = editor.querySelector(
        `[data-following-action-editor][data-visual-id="${CSS.escape(id)}"]`,
      );
      return {
        id,
        visual_description: editableText(description),
        ...(action ? { exact_action: editableText(action) } : {}),
      };
    });

    const applySavedContent = (content) => {
      if (content?.script?.titles?.length === titleOptions.length) {
        titleOptions.forEach((option, index) => {
          option.value = content.script.titles[index];
        });
        titleIndex = 0;
        renderTitle();
      }
      if (!visualTimeline || !content?.script?.words) return;
      const words = content.script.words;
      const positions = new Map(words.map((word, index) => [word.id, index]));
      const visualElements = Object.values(content.visual_tracks || {}).flat();
      const elements = [
        ...visualElements,
        ...(content.subtitle_directives || []).map((directive) => ({
          ...directive,
          visual_description: directive.mode === "hidden"
            ? `Hide subtitles over “${content.script.narration.slice(
              words[positions.get(directive.start_word_id)].start_char,
              words[positions.get(directive.end_word_id)].end_char,
            )}”`
            : `Emphasize “${content.script.narration.slice(
              words[positions.get(directive.start_word_id)].start_char,
              words[positions.get(directive.end_word_id)].end_char,
            )}”`,
        })),
      ];
      const byId = new Map(elements.map((element) => [element.id, element]));

      visualTimeline.querySelectorAll("[data-element-id]").forEach((item) => {
        const element = byId.get(item.dataset.elementId);
        if (!element) {
          item.remove();
          editor.querySelectorAll(
            `[data-contributor-visual-id="${CSS.escape(item.dataset.elementId)}"]`,
          ).forEach((duplicate) => duplicate.remove());
          return;
        }
        const start = positions.get(element.start_word_id);
        const end = positions.get(element.end_word_id);
        item.dataset.startIndex = String(start);
        item.dataset.endIndex = String(end);
        item.style.setProperty("--word-start", String(start + 1));
        item.style.setProperty("--word-span", String(end - start + 1));
        const scriptText = content.script.narration.slice(
          words[start].start_char,
          words[end].end_char,
        );
        const timelineScript = item.querySelector(".format-timeline-script");
        const description = item.querySelector(".format-timeline-visual");
        if (timelineScript) timelineScript.textContent = scriptText;
        if (description && !description.matches(":focus")) {
          description.textContent = element.visual_description;
        }
      });

      const baseBlocks = content.visual_tracks?.base || [];
      const axis = visualTimeline.querySelector(".format-word-axis");
      if (axis) {
        axis.replaceChildren(...baseBlocks.map((block) => {
          const start = positions.get(block.start_word_id);
          const end = positions.get(block.end_word_id);
          const section = document.createElement("p");
          section.className = "format-word-axis-section";
          section.dataset.baseScriptSection = block.id;
          section.style.setProperty("--word-start", String(start + 1));
          section.style.setProperty("--word-span", String(end - start + 1));
          for (let index = start; index <= end; index += 1) {
            if (index > start) section.append(" ");
            const word = document.createElement("span");
            word.dataset.axisWordIndex = String(index);
            word.textContent = words[index].text;
            section.append(word);
          }
          return section;
        }));
        axis.style.setProperty("--word-count", String(words.length));
      }
      visualTimeline.style.setProperty("--word-count", String(words.length));
      visualTimeline.querySelectorAll(".format-timeline-track").forEach((track) => {
        track.style.setProperty("--word-count", String(words.length));
      });
      const meta = editor.querySelector(".format-script-meta");
      if (meta) {
        const aspectRatio = meta.textContent.split("·").at(-1).trim();
        meta.textContent = `${content.script.estimated_duration_seconds} sec · ${aspectRatio}`;
      }
      refreshTimelineColumns();
    };

    const saveEdits = async () => {
      clearTimeout(saveTimer);
      if (editingDisabled || saving || !editor.dataset.autosaveUrl) return;
      saving = true;
      const sentRevision = editRevision;
      showSaveState("pending", "Saving…");
      try {
        const response = await fetch(editor.dataset.autosaveUrl, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            generated_base_version_id: editor.dataset.generatedBaseVersionId,
            narration: editableText(scriptEditor),
            visual_edits: collectVisualEdits(),
            ...(titleOptions.length ? { titles: titles() } : {}),
          }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Changes could not be saved.");
        applySavedContent(result.content);
        saving = false;
        if (editRevision !== sentRevision) saveEdits();
        else showSaveState("saved", "Saved automatically");
      } catch (error) {
        saving = false;
        showSaveState("failed", error.message);
      }
    };

    const queueSave = () => {
      editRevision += 1;
      clearTimeout(saveTimer);
      showSaveState("pending", "Saving…");
      saveTimer = setTimeout(saveEdits, 500);
    };

    if (!editingDisabled) {
      editor.addEventListener("input", (event) => {
        if (event.target.closest?.("[data-title-editor]")) {
          const ranked = titles();
          ranked[titleIndex] = editableText(titleEditor);
          if (titleIndex !== 0) {
            const [edited] = ranked.splice(titleIndex, 1);
            ranked.unshift(edited);
            titleIndex = 0;
          }
          titleOptions.forEach((option, optionIndex) => {
            option.value = ranked[optionIndex];
          });
          updateTitleOutputs(ranked[0]);
          if (titlePosition) titlePosition.textContent = `1 / ${titleOptions.length}`;
          if (titleSelected) titleSelected.hidden = false;
          if (titleSelect) titleSelect.hidden = true;
          queueSave();
          return;
        }
        const description = event.target.closest?.("[data-visual-description-editor]");
        if (description) {
          editor.querySelectorAll(
            `[data-contributor-visual-description="${CSS.escape(description.dataset.visualId)}"]`,
          ).forEach((duplicate) => {
            duplicate.textContent = editableText(description);
          });
        }
        if (
          event.target.closest?.(
            "[data-script-editor], [data-visual-description-editor], [data-following-action-editor]",
          )
        ) {
          queueSave();
        }
      });
      editor.addEventListener("focusout", (event) => {
        if (event.target.closest?.(
          "[data-title-editor], [data-script-editor], [data-visual-description-editor], [data-following-action-editor]",
        )) saveEdits();
      });
      editor.addEventListener("keydown", (event) => {
        if (
          event.key === "Enter"
          && event.target.closest?.(
            "[data-title-editor], [data-visual-description-editor], [data-following-action-editor]",
          )
        ) {
          event.preventDefault();
          if (event.target.closest?.("[data-title-editor]")) event.target.blur();
        }
      });
    }

    titleCarousel?.addEventListener("click", (event) => {
      if (event.target.closest("[data-title-previous]")) {
        titleIndex = (titleIndex - 1 + titleOptions.length) % titleOptions.length;
        renderTitle();
      } else if (event.target.closest("[data-title-next]")) {
        titleIndex = (titleIndex + 1) % titleOptions.length;
        renderTitle();
      } else if (event.target.closest("[data-title-select]")) {
        selectTitle(titleIndex);
      }
    });
    renderTitle();

    const clearPendingHighlight = () => {
      CSS.highlights?.delete("pending-comment-selection");
      fallbackHighlights.forEach((highlight) => highlight.remove());
      fallbackHighlights = [];
    };

    const showPendingHighlight = (range) => {
      clearPendingHighlight();
      if (typeof Highlight !== "undefined" && CSS.highlights) {
        CSS.highlights.set(
          "pending-comment-selection",
          new Highlight(range.cloneRange()),
        );
        return;
      }

      fallbackHighlights = [...range.getClientRects()].map((rect) => {
        const highlight = document.createElement("span");
        highlight.className = "format-pending-selection-highlight";
        Object.assign(highlight.style, {
          left: `${rect.left}px`,
          top: `${rect.top}px`,
          width: `${rect.width}px`,
          height: `${rect.height}px`,
        });
        document.body.append(highlight);
        return highlight;
      });
    };

    const fitScriptToPage = () => {
      if (!scriptBody || !focus) return;
      if (window.matchMedia("(max-width: 760px)").matches) {
        scriptBody.classList.remove("is-condensed", "is-three-column");
        return;
      }

      const pages = Number.parseInt(focus.dataset.scriptPages || "1", 10);
      scriptBody.classList.toggle("is-condensed", pages >= 2);
      scriptBody.classList.toggle("is-three-column", pages === 3);
    };

    const setScriptPages = (pages) => {
      focus.dataset.scriptPages = String(pages);
      editor.querySelectorAll("[data-script-pages-button]").forEach((button) => {
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.scriptPagesButton === String(pages)),
        );
      });
      fitScriptToPage();
    };

    const selectDefaultScriptPages = () => {
      if (window.matchMedia("(max-width: 760px)").matches) return;
      setScriptPages(2);
      if (scriptBody.getBoundingClientRect().height > window.innerHeight * 0.7 + 1) {
        setScriptPages(3);
      }
    };

    const syncCommentRailHeight = () => {
      if (!focus || !scriptBody) return;
      if (window.matchMedia("(max-width: 760px)").matches) {
        focus.style.removeProperty("--script-content-height");
        return;
      }
      focus.style.setProperty("--script-content-height", "0px");
      const scriptHeight = scriptBody.getBoundingClientRect().height;
      focus.style.setProperty("--script-content-height", `${scriptHeight}px`);
    };

    const refreshCommentPreviews = () => {
      if (!threadLayer) return;
      const collapsedHeight = Math.max(52, Math.floor(threadLayer.clientHeight / 3));
      threadLayer.style.setProperty(
        "--comment-card-collapsed-height",
        `${collapsedHeight}px`,
      );
      threadLayer.querySelectorAll("[data-inline-comment-preview]").forEach((preview) => {
        const quote = preview.querySelector("[data-full-quote]");
        if (quote) {
          const fullQuote = quote.dataset.fullQuote;
          const renderQuote = (retainedCharacters) => {
            const startLength = Math.ceil(retainedCharacters / 2);
            const endLength = Math.floor(retainedCharacters / 2);
            const end = endLength ? fullQuote.slice(-endLength) : "";
            quote.textContent = retainedCharacters < fullQuote.length
              ? `“${fullQuote.slice(0, startLength)}…${end}”`
              : `“${fullQuote}”`;
          };

          renderQuote(fullQuote.length);
          if (!preview.closest(".is-editing")) {
            const lineHeight = Number.parseFloat(getComputedStyle(quote).lineHeight);
            const maximumHeight = lineHeight * 2 + 1;
            if (quote.scrollHeight > maximumHeight) {
              let lowerBound = 0;
              let upperBound = fullQuote.length - 1;
              while (lowerBound < upperBound) {
                const candidate = Math.ceil((lowerBound + upperBound) / 2);
                renderQuote(candidate);
                if (quote.scrollHeight <= maximumHeight) lowerBound = candidate;
                else upperBound = candidate - 1;
              }
              renderQuote(lowerBound);
            }
          }
        }

        preview.classList.remove("is-truncated");
        preview.classList.toggle(
          "is-truncated",
          preview.scrollHeight > preview.clientHeight + 1,
        );
      });
    };

    const resizeInlineCommentInput = (input) => {
      input.style.height = "auto";
      const borderHeight = input.offsetHeight - input.clientHeight;
      input.style.height = `${input.scrollHeight + borderHeight}px`;
    };

    const refreshTimelineColumns = () => {
      if (!visualTimeline) return;
      const words = [...visualTimeline.querySelectorAll("[data-axis-word-index]")];
      if (!words.length) return;

      const context = document.createElement("canvas").getContext("2d");
      context.font = getComputedStyle(words[0]).font;
      const hasBaseScriptSections = Boolean(
        visualTimeline.querySelector("[data-base-script-section]"),
      );
      const widths = words.map((word) => (
        hasBaseScriptSections
          ? Math.max(14, (context.measureText(`${word.textContent} `).width + 2) * 0.6)
          : Math.max(24, context.measureText(word.textContent).width + 8)
      ));
      const minimumBlockWidth = Number.parseFloat(
        getComputedStyle(visualTimeline).getPropertyValue(
          "--minimum-timeline-block-width",
        ),
      ) || 200;

      visualTimeline
        .querySelectorAll('[data-track-key="base"] [data-start-index][data-end-index]')
        .forEach((item) => {
          const start = Number.parseInt(item.dataset.startIndex, 10);
          const end = Number.parseInt(item.dataset.endIndex, 10);
          if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
            return;
          }
          const spanWidth = widths
            .slice(start, end + 1)
            .reduce((total, width) => total + width, 0);
          if (spanWidth >= minimumBlockWidth) return;
          const additionalWidth = (minimumBlockWidth - spanWidth) / (end - start + 1);
          for (let index = start; index <= end; index += 1) {
            widths[index] += additionalWidth;
          }
        });

      const template = widths.map((width) => `${Math.ceil(width)}px`).join(" ");
      const contentWidth = widths.reduce((total, width) => total + Math.ceil(width), 0);
      visualTimeline.style.setProperty("--word-columns", template);
      visualTimeline.style.setProperty("--timeline-content-width", `${contentWidth}px`);
    };

    const closeVisualCommentForms = (except = null) => {
      editor.querySelectorAll("[data-element-comment-form]").forEach((form) => {
        if (form === except) return;
        form.hidden = true;
        form.closest(".format-timeline-item")?.classList.remove("is-commenting");
        form.closest(".format-timeline-item")
          ?.querySelectorAll("[data-element-comment-toggle]")
          .forEach((toggle) => toggle.setAttribute("aria-expanded", "false"));
      });
    };

    const centerCommentCard = (card) => {
      card?.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "nearest",
      });
    };

    const centerTimelineItem = (item) => {
      if (!item || visualTimeline?.dataset.view !== "timeline") return;
      const itemLeft = item.getBoundingClientRect().left
        - visualTimeline.getBoundingClientRect().left
        + visualTimeline.scrollLeft;
      const centeredLeft = itemLeft - (visualTimeline.clientWidth - item.offsetWidth) / 2;
      const maximumLeft = Math.max(0, visualTimeline.scrollWidth - visualTimeline.clientWidth);
      visualTimeline.scrollTo({
        left: Math.max(0, Math.min(centeredLeft, maximumLeft)),
        behavior: "smooth",
      });
    };

    const setLinkedWords = (startIndex, endIndex) => {
      scriptDocument?.querySelectorAll("[data-script-word-index]").forEach((word) => {
        const index = Number.parseInt(word.dataset.scriptWordIndex, 10);
        word.classList.toggle(
          "is-linked-word",
          startIndex !== null && startIndex <= index && index <= endIndex,
        );
      });
      visualTimeline?.querySelectorAll("[data-axis-word-index]").forEach((word) => {
        const index = Number.parseInt(word.dataset.axisWordIndex, 10);
        word.classList.toggle(
          "is-linked-word",
          startIndex !== null && startIndex <= index && index <= endIndex,
        );
      });
    };

    const colorScriptWordsForGridTrack = () => {
      const words = [...(scriptDocument?.querySelectorAll("[data-script-word-index]") || [])];
      words.forEach((word) => {
        word.classList.remove("is-grid-track-word");
        word.style.removeProperty("--grid-track-word-color");
      });
      if (visualTimeline?.dataset.view !== "grid") return;

      const trackKey = visualTimeline.dataset.gridTrack;
      const track = visualTimeline.querySelector(
        `[data-track-key="${CSS.escape(trackKey)}"]`,
      );
      track?.querySelectorAll("[data-start-index]").forEach((item, blockIndex) => {
        const startIndex = Number.parseInt(item.dataset.startIndex, 10);
        const endIndex = Number.parseInt(item.dataset.endIndex, 10);
        const color = visualBlockTextColors[blockIndex % visualBlockTextColors.length];
        words.forEach((word) => {
          const wordIndex = Number.parseInt(word.dataset.scriptWordIndex, 10);
          if (startIndex <= wordIndex && wordIndex <= endIndex) {
            word.classList.add("is-grid-track-word");
            word.style.setProperty("--grid-track-word-color", color);
          }
        });
      });
    };

    const selectElementsForRange = (startIndex, endIndex, source) => {
      activeVisualSource = source;
      let firstSelectedItem = null;
      visualTimeline?.querySelectorAll("[data-start-index]").forEach((item) => {
        const itemStart = Number.parseInt(item.dataset.startIndex, 10);
        const itemEnd = Number.parseInt(item.dataset.endIndex, 10);
        const selected = startIndex !== null && itemStart <= endIndex && startIndex <= itemEnd;
        item.querySelector(".format-timeline-card")?.classList.toggle(
          "is-linked-visual",
          selected,
        );
        if (selected && !firstSelectedItem) firstSelectedItem = item;
      });
      centerTimelineItem(firstSelectedItem);
    };

    const wordRangeForNodes = (nodes) => {
      const indexes = nodes
        .map((word) => Number.parseInt(word.dataset.scriptWordIndex, 10))
        .filter(Number.isInteger);
      return indexes.length ? [Math.min(...indexes), Math.max(...indexes)] : [null, null];
    };

    const selectBeatForClick = (beat) => {
      const [startIndex, endIndex] = wordRangeForNodes([
        ...beat.querySelectorAll("[data-script-word-index]"),
      ]);
      setLinkedWords(startIndex, endIndex);
      selectElementsForRange(startIndex, endIndex, "script-click");
    };

    const selectVisualsForComment = (commentId) => {
      const words = [...scriptDocument.querySelectorAll("mark[data-comment-ids]")]
        .filter((mark) => mark.dataset.commentIds.split(" ").includes(commentId))
        .flatMap((mark) => [...mark.querySelectorAll("[data-script-word-index]")]);
      const [startIndex, endIndex] = wordRangeForNodes(words);
      setLinkedWords(startIndex, endIndex);
      selectElementsForRange(startIndex, endIndex, "comment");
    };

    const clearScriptVisualSelection = () => {
      if (activeVisualSource === "script") {
        setLinkedWords(null, null);
        selectElementsForRange(null, null, null);
      }
    };

    const closeSelectionForm = ({ reset = true } = {}) => {
      if (!selectionForm) {
        clearPendingHighlight();
        pendingSelection = null;
        return;
      }
      selectionForm.hidden = true;
      if (reset) selectionForm.reset();
      clearPendingHighlight();
      pendingSelection = null;
    };

    const readSelection = () => {
      if (!selectionForm || (!editingDisabled && scriptEditor)) {
        closeSelectionForm();
        return;
      }
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount !== 1) {
        clearScriptVisualSelection();
        if (!selectionForm.contains(document.activeElement)) closeSelectionForm();
        return;
      }
      const range = selection.getRangeAt(0);
      const startBeat = closestBeat(range.startContainer);
      const endBeat = closestBeat(range.endContainer);
      if (
        !startBeat ||
        !endBeat ||
        !scriptDocument.contains(startBeat) ||
        !scriptDocument.contains(endBeat)
      ) {
        clearScriptVisualSelection();
        closeSelectionForm();
        return;
      }

      const rawText = range.toString();
      const leadingWhitespace = rawText.length - rawText.trimStart().length;
      const trailingWhitespace = rawText.length - rawText.trimEnd().length;
      const start = rangeOffset(startBeat, range.startContainer, range.startOffset) + leadingWhitespace;
      const end = rangeOffset(endBeat, range.endContainer, range.endOffset) - trailingWhitespace;
      const text = rawText.trim();
      if (!text || (startBeat === endBeat && end <= start)) {
        clearScriptVisualSelection();
        closeSelectionForm();
        return;
      }

      const selectedWords = [...scriptDocument.querySelectorAll("[data-script-word-index]")]
        .filter((word) => range.intersectsNode(word));
      const [selectedStartIndex, selectedEndIndex] = wordRangeForNodes(selectedWords);
      setLinkedWords(selectedStartIndex, selectedEndIndex);
      selectElementsForRange(selectedStartIndex, selectedEndIndex, "script");
      if (commentsDisabled) {
        closeSelectionForm();
        return;
      }

      const rect = range.getBoundingClientRect();
      pendingSelection = {
        target: startBeat.dataset.narrationTarget,
        endTarget: endBeat.dataset.narrationTarget,
        start,
        end,
        text,
      };
      selectionForm.elements.namedItem("narration_target").value = pendingSelection.target;
      selectionForm.elements.namedItem("range_end_target").value = pendingSelection.endTarget;
      selectionForm.elements.namedItem("range_start").value = pendingSelection.start;
      selectionForm.elements.namedItem("range_end").value = pendingSelection.end;
      showPendingHighlight(range);
      selectionForm.hidden = false;

      const left = Math.max(
        8,
        Math.min(
          window.innerWidth - selectionForm.offsetWidth - 8,
          rect.left + rect.width / 2 - selectionForm.offsetWidth / 2,
        ),
      );
      const above = rect.top - selectionForm.offsetHeight - 8;
      selectionForm.style.left = `${left}px`;
      selectionForm.style.top = `${above >= 8 ? above : rect.bottom + 8}px`;
      selectionInput.focus({ preventScroll: true });
    };

    scriptDocument?.addEventListener("mouseup", (event) => {
      const clickedBeat = closestBeat(event.target);
      const clickedComment = event.target.closest?.("mark[data-comment-ids]");
      setTimeout(() => {
        if (window.getSelection()?.isCollapsed && clickedBeat && !clickedComment) {
          closeSelectionForm();
          selectBeatForClick(clickedBeat);
          return;
        }
        readSelection();
      });
    });
    scriptDocument?.addEventListener("keyup", readSelection);
    if (!commentsDisabled) {
      scriptDocument?.addEventListener("scroll", () => closeSelectionForm());
      window.addEventListener("scroll", () => closeSelectionForm(), { passive: true });
    }

    selectionInput?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      selectionForm.requestSubmit();
    });
    selectionInput?.addEventListener("input", () => {
      selectionInput.scrollLeft = selectionInput.scrollWidth;
    });
    selectionForm?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSelectionForm();
    });

    const resizeGeneralCommentInput = () => {
      if (!generalCommentInput) return;
      generalCommentInput.style.height = "auto";
      const maxHeight = Number.parseFloat(
        getComputedStyle(generalCommentInput).maxHeight,
      );
      const height = Math.min(generalCommentInput.scrollHeight, maxHeight);
      generalCommentInput.style.height = `${height}px`;
      generalCommentInput.style.overflowY =
        generalCommentInput.scrollHeight > maxHeight ? "auto" : "hidden";
    };
    generalCommentInput?.addEventListener("input", resizeGeneralCommentInput);
    generalCommentInput?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      generalCommentInput.form.requestSubmit();
    });
    resizeGeneralCommentInput();

    threadLayer?.addEventListener("input", (event) => {
      const input = event.target.closest('[data-inline-comment-edit] textarea[name="comment_text"]');
      if (!input) return;
      resizeInlineCommentInput(input);
    });

    editor.addEventListener("input", (event) => {
      const input = event.target.closest("[data-visual-comment-input]");
      if (input) resizeInlineCommentInput(input);
    });

    editor.addEventListener("keydown", (event) => {
      const input = event.target.closest("[data-visual-comment-input]");
      if (!input) return;
      if (event.key === "Escape") {
        closeVisualCommentForms();
        input.form.reset();
        return;
      }
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      input.form.requestSubmit();
    });

    editor.addEventListener("click", (event) => {
      const visualCommentToggle = event.target.closest("[data-element-comment-toggle]");
      if (visualCommentToggle) {
        const item = visualCommentToggle.closest(".format-timeline-item");
        const form = document.getElementById(visualCommentToggle.dataset.commentFormId);
        const shouldOpen = form.hidden;
        closeVisualCommentForms(shouldOpen ? form : null);
        form.hidden = !shouldOpen;
        item.classList.toggle("is-commenting", shouldOpen);
        visualCommentToggle.setAttribute("aria-expanded", String(shouldOpen));
        if (shouldOpen) {
          const input = form.querySelector("[data-visual-comment-input]");
          resizeInlineCommentInput(input);
          input.focus({ preventScroll: true });
        }
      }

      const viewButton = event.target.closest("[data-timeline-view]");
      if (viewButton) {
        visualTimeline.dataset.view = viewButton.dataset.timelineView;
        editor.classList.toggle("is-grid-view", viewButton.dataset.timelineView === "grid");
        editor.querySelectorAll("[data-timeline-view]").forEach((button) => {
          button.setAttribute("aria-pressed", String(button === viewButton));
        });
        centerTimelineItem(
          visualTimeline.querySelector(".is-linked-visual")?.closest("[data-start-index]"),
        );
        colorScriptWordsForGridTrack();
      }

      const gridTrackButton = event.target.closest("[data-grid-track]");
      if (gridTrackButton) {
        visualTimeline.dataset.gridTrack = gridTrackButton.dataset.gridTrack;
        editor.querySelectorAll("button[data-grid-track]").forEach((button) => {
          button.setAttribute("aria-pressed", String(button === gridTrackButton));
        });
        colorScriptWordsForGridTrack();
      }

      const scriptButton = event.target.closest("[data-timeline-script]");
      if (scriptButton) {
        const scriptsHidden = scriptButton.dataset.timelineScript === "hide";
        visualTimeline.classList.toggle("is-script-hidden", scriptsHidden);
        editor.querySelectorAll("[data-timeline-script]").forEach((button) => {
          button.setAttribute("aria-pressed", String(button === scriptButton));
        });
      }

      const pageButton = event.target.closest("[data-script-pages-button]");
      if (pageButton) {
        scriptPagesManuallySelected = true;
        setScriptPages(Number.parseInt(pageButton.dataset.scriptPagesButton, 10));
        refreshLayout();
      }

      const timelineCard = event.target.closest(".format-timeline-card");
      if (timelineCard && !event.target.closest("[data-element-comment-toggle]")) {
        const item = timelineCard.closest("[data-start-index]");
        const startIndex = Number.parseInt(item.dataset.startIndex, 10);
        const endIndex = Number.parseInt(item.dataset.endIndex, 10);
        setLinkedWords(startIndex, endIndex);
        visualTimeline.querySelectorAll(".format-timeline-card").forEach((card) => {
          card.classList.toggle("is-linked-visual", card === timelineCard);
        });
        activeVisualSource = "element";
      }

      const preview = event.target.closest("[data-inline-comment-preview]");
      if (preview) {
        const commentEditor = preview.closest("[data-inline-comment-edit]");
        selectVisualsForComment(commentEditor.dataset.commentCard);
        if (commentEditor.classList.contains("is-editing")) return;
        commentEditor.classList.add("is-editing");
        preview.setAttribute("aria-expanded", "true");
        const fields = commentEditor.querySelector("[data-inline-comment-edit-fields]");
        fields.hidden = false;
        refreshCommentPreviews();
        const input = fields.querySelector('textarea[name="comment_text"]');
        resizeInlineCommentInput(input);
        input.focus({ preventScroll: true });
        centerCommentCard(commentEditor);
      }

      const cancel = event.target.closest("[data-inline-comment-cancel]");
      if (cancel) {
        const commentEditor = cancel.closest("[data-inline-comment-edit]");
        const preview = commentEditor.querySelector("[data-inline-comment-preview]");
        const input = commentEditor.querySelector('[name="comment_text"]');
        input.value = preview.querySelector("[data-comment-full]").textContent;
        commentEditor.classList.remove("is-editing");
        preview.setAttribute("aria-expanded", "false");
        commentEditor.querySelector("[data-inline-comment-edit-fields]").hidden = true;
        commentEditor.querySelector(".format-comment-status").textContent = "";
        refreshCommentPreviews();
      }

      const mark = event.target.closest("mark[data-comment-ids]");
      if (mark && !window.getSelection()?.toString()) {
        const commentId = mark.dataset.commentIds.split(" ")[0];
        selectVisualsForComment(commentId);
        const card = threadLayer.querySelector(`[data-comment-card="${CSS.escape(commentId)}"]`);
        centerCommentCard(card);
        card?.classList.add("is-active");
        setTimeout(() => card?.classList.remove("is-active"), 1300);
      }
    });

    document.addEventListener("click", (event) => {
      if (
        activeVisualSource !== "script-click" ||
        event.target.closest?.(".format-document-beat")
      ) {
        return;
      }
      setLinkedWords(null, null);
      selectElementsForRange(null, null, null);
    });

    threadLayer?.addEventListener("pointerover", (event) => {
      const card = event.target.closest("[data-comment-card]");
      if (!card) return;
      const commentId = card.dataset.commentCard;
      scriptDocument.querySelectorAll("mark[data-comment-ids]").forEach((mark) => {
        mark.classList.toggle("is-active", mark.dataset.commentIds.split(" ").includes(commentId));
      });
    });
    threadLayer?.addEventListener("pointerout", (event) => {
      if (event.relatedTarget && threadLayer.contains(event.relatedTarget)) return;
      scriptDocument.querySelectorAll("mark.is-active").forEach((mark) => mark.classList.remove("is-active"));
    });

    editor.querySelector("[data-version-selector]")?.addEventListener("change", (event) => {
      window.location.assign(event.target.value);
    });

    const copyWidget = editor.querySelector(".format-script-copy-ids");
    copyWidget?.querySelector("button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      try {
        await navigator.clipboard.writeText(copyWidget.querySelector("code").textContent);
        button.textContent = "Copied";
        setTimeout(() => {
          button.textContent = "Copy IDs";
        }, 1600);
      } catch {
        button.textContent = "Copy failed";
      }
    });

    const copyRichText = async (html, plainText) => {
      if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([plainText], { type: "text/plain" }),
          }),
        ]);
        return;
      }

      let copied = false;
      const handleCopy = (event) => {
        event.clipboardData.setData("text/html", html);
        event.clipboardData.setData("text/plain", plainText);
        event.preventDefault();
        copied = true;
      };
      document.addEventListener("copy", handleCopy, { once: true });
      try {
        document.execCommand("copy");
      } finally {
        document.removeEventListener("copy", handleCopy);
      }
      if (!copied) throw new Error("Styled export could not be copied.");
    };

    const exportButton = editor.querySelector("[data-copy-export-button]");
    const exportLabel = exportButton?.querySelector("[data-copy-export-label]");
    const exportStatus = editor.querySelector("[data-copy-export-status]");
    const exportSource = editor.querySelector("[data-copy-export-source]");
    const exportPlain = editor.querySelector("[data-copy-export-plain]");
    exportButton?.addEventListener("click", async () => {
      exportButton.disabled = true;
      exportButton.classList.remove("is-copied", "is-failed");
      try {
        await saveEdits();
        if (saving || editor.dataset.autosaveState === "failed") {
          throw new Error("Finish saving before exporting.");
        }
        // Export the saved edits, not the hidden snapshot rendered on first load.
        const response = await fetch(window.location.href, { cache: "no-store" });
        if (!response.ok) throw new Error("Export could not be refreshed.");
        const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
        exportSource.innerHTML = fresh.querySelector("[data-copy-export-source]").innerHTML;
        exportPlain.value = fresh.querySelector("[data-copy-export-plain]").value;
        await copyRichText(exportSource.innerHTML.trim(), exportPlain.value.trim());
        exportButton.classList.add("is-copied");
        exportLabel.textContent = "Copied with Styling";
        exportStatus.textContent = "Styled export copied. Paste it into Google Docs.";
      } catch (error) {
        exportButton.classList.add("is-failed");
        exportLabel.textContent = "Copy Failed";
        exportStatus.textContent = `The styled export could not be copied: ${error.message}`;
      } finally {
        setTimeout(() => {
          exportButton.disabled = false;
          exportButton.classList.remove("is-copied", "is-failed");
          exportLabel.textContent = "Copy Export";
        }, 1800);
      }
    });

    editor.addEventListener("submit", async (event) => {
      const form = event.target.closest("[data-script-comment-form], [data-inline-comment-edit]");
      if (!form || !editor.contains(form)) return;
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const status = form.querySelector(".format-comment-status");
      if (button) button.disabled = true;
      status.textContent = "";

      try {
        const response = await fetch(form.action, {
          method: form.matches("[data-inline-comment-edit]") ? "PUT" : "POST",
          body: new FormData(form),
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error("Comment could not be saved.");
        const result = await response.json();

        if (form.matches("[data-element-comment-form]")) {
          const item = form.closest(".format-timeline-item");
          const badge = item.querySelector("[data-visual-comment-count]");
          const count = Number.parseInt(badge.textContent || "0", 10) + 1;
          badge.textContent = String(count);
          badge.hidden = false;
          badge.setAttribute(
            "aria-label",
            `${count} ${count === 1 ? "comment" : "comments"} on this visual`,
          );
          form.reset();
          closeVisualCommentForms();
          return;
        }

        if (
          form.matches("[data-selection-comment-form], [data-general-comment-form]") ||
          result.deleted
        ) {
          window.location.reload();
          return;
        }

        const preview = form.querySelector("[data-inline-comment-preview]");
        const text = result.comment.feedback_text;
        preview.querySelector("[data-comment-summary]").textContent = text;
        preview.querySelector("[data-comment-full]").textContent = text;
        form.querySelector('[name="comment_text"]').value = text;
        form.classList.remove("is-editing");
        preview.setAttribute("aria-expanded", "false");
        form.querySelector("[data-inline-comment-edit-fields]").hidden = true;
        refreshCommentPreviews();
      } catch (error) {
        status.textContent = error.message;
      } finally {
        if (button) button.disabled = false;
      }
    });

    const refreshLayout = () => {
      fitScriptToPage();
      syncCommentRailHeight();
      refreshCommentPreviews();
      refreshTimelineColumns();
    };
    document.fonts?.ready.then(() => {
      if (!scriptPagesManuallySelected) selectDefaultScriptPages();
      refreshLayout();
    });
    new ResizeObserver(refreshLayout).observe(focus);
    window.addEventListener("resize", () => {
      if (!scriptPagesManuallySelected) selectDefaultScriptPages();
      refreshLayout();
    });
    selectDefaultScriptPages();
    refreshLayout();
  });
})();
