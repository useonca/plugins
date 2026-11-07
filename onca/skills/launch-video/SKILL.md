---
name: launch-video
description: Onca's method for a product launch, ad or social video, made free on the founder's Mac from the product's real UI. Hook, info, closure; research creative mechanisms; five concepts on five different mechanisms; the founder picks; parallel builds; a contact-sheet self-review; the founder watches with sound on; save to the Onca library and post with the founder's approval. Use for any launch video, product video, ad creative, reel, TikTok or Short about a software product.
---

# Launch video

The Onca method for short vertical videos (15 to 25 seconds, 9:16) that explain a software product with its real UI, at no generation cost. It works for any product. Rendering is the `video-render` skill's job, editing a recording is `video-edit`'s and narration is `voice`'s; carousels and still images are `carousel-render`'s; paths are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the video's own folder.

## Step 0: is this plugin current?

1. Call Onca's `get_launch_overview` and read `plugin.version`.
2. Run `python3 ../video-render/scripts/doctor.py check-update --latest <that version>`.
3. `outdated`: tell the founder "The Onca plugin has an update (<installed> to <latest>)", then run the update commands for this client from `plugin.update`, then ask the founder to type `/reload-plugins` in Claude Code (a slash command only they can run) or to start a new session (Codex: a new session); until then this session still has the old skills. If the update finds nothing newer, keep the installed version and go on.
4. `current`, `newer` or `unknown`: go on.
5. Before the first video of a session, run `python3 ../video-render/scripts/doctor.py check` and handle what is missing as the `video-render` skill says.

## The method

1. **Facts and brand.** Read the product's facts (its repo or docs, read only: features, defaults, limits), its look (logo, colours, fonts, real UI screens or markup) and the founder's brief; `get_project_profile` has the positioning. A video claims only what the product does. Demo data only.
2. **Structure.** Every video is a HOOK (the first 1 to 3 seconds make the viewer feel something and want an answer), the INFO (the value shown in real UI) and the CLOSURE (the last seconds answer the hook literally).
3. **Research mechanisms, not "best ads".** Study creative mechanisms (`references/mechanisms.md`), the platform's own creative rules and what reads as cheap or premium. Keep each source and how sure it is.
4. **Five concepts on five different mechanisms**, never five versions of one idea. Each: name and one-line premise; hook (what is on screen, what the viewer feels, which question it opens); info; closure (how the question is answered, last frame); why it works; production route (free motion design, or the paid shot it would need, described and not generated); risk. Rank them.
5. **The founder picks**: one, a pair with the most different hooks to A/B, or all.
6. **Build every pick at the same time**, one project folder per concept, all from one shared brief (`references/build-rules.md`). Write each composition with the `hyperframes` skill and render it with `video-render`.
7. **Self-review** each video on its 14-frame contact sheet (`video-render`'s step 4): small type, text outside the safe box (for Instagram, the middle 4:5: y 285 to 1635; not verified, Instagram publishes no numbers for its feed crop, so check a real post before a paid ad), two changes at once, a claim the product cannot back. Fix, render again. Check the length against the read time.
8. **The founder watches every video with sound on** and picks the winner (you cannot hear the mix: say so). Fix weak spots in the winner only.

## Save and post

- Save each kept video with Onca's `library_upload`: `name`, a `description` (required: the concept, the hook on screen, 9:16 or 16:9, the last frame), the spoken words or captions as `transcript`, `service: "onca"`, `model: "Onca video"`, the concept in `notes`, the script as `prompt`, no `cost` (it was free). Never put a rendering tool's name (HyperFrames, mlx-audio, Chatterbox, parakeet) in any library field. Run the `curl` line it returns within the hour; a file is up to 50 MB. `library_list` shows it saved.
- Post with Onca's `schedule_post`, the saved video as media; the founder approves every post. A TikTok post also needs its `tiktok` settings, which the founder picks. Music: on a business account the founder adds a licensed sound from the platform's own library when posting.
- Fit each post to its platform before scheduling: length, format and caption rules are in Onca's playbook platform-fit (get_playbook("platform-fit")); a video for Instagram, TikTok and Facebook is exported without another app's logo.

## Hard lines

- No AI people: no generated presenters, avatars, stock faces or cloned voices of anyone but the founder (with consent, the `voice` skill).
- Real UI and true claims only; no wording that overclaims; no secrets or real customer data on screen.
- No paid generation without Onca's content guide's free price check and the founder's yes for that exact run (`get_content_guide`). Never the engine's cloud render, publish or anything else that spends.
- No em or en dashes in on-screen text; a plain hyphen.
