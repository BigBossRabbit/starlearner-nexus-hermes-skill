# Handling User Requests for Documents

When a user asks to view or listen to a document (e.g., a guide, README, or notes):

1. **Verify file existence** first using appropriate tools (e.g., `search_files` to locate, `read_file` to confirm).
2. If the file is not found:
   - Inform the user clearly that the file could not be located at the expected path.
   - Offer to search for similar files or ask if they have an alternative location/name.
   - Do not proceed with unrelated updates; stay focused on fulfilling the request.
3. If the user requests a voice note or audio version:
   - Use the `text_to_speech` tool to generate audio from the document content.
   - Provide the audio as a media attachment, noting the format and duration if relevant.
4. After delivering the requested content, ask if they need anything else related to the document before moving on to other topics.

This ensures responsiveness, reduces off-topic tangents, and respects the user's immediate context.