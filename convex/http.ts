import { httpRouter } from "convex/server";
import { WebhookEvent } from "@clerk/nextjs/server";
import { Webhook } from "svix";
import { api } from "./_generated/api";
import { httpAction } from "./_generated/server";

const http = httpRouter();

// Clerk webhook route
http.route({
  path: "/clerk-webhook",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const webhookSecret = process.env.CLERK_WEBHOOK_SECRET;
    if (!webhookSecret) {
      throw new Error("Missing CLERK_WEBHOOK_SECRET environment variable");
    }

    const svix_id = request.headers.get("svix-id");
    const svix_signature = request.headers.get("svix-signature");
    const svix_timestamp = request.headers.get("svix-timestamp");

    if (!svix_id || !svix_signature || !svix_timestamp) {
      return new Response("No svix headers found", { status: 400 });
    }

    const payload = await request.json();
    const body = JSON.stringify(payload);

    const wh = new Webhook(webhookSecret);
    let evt: WebhookEvent;

    try {
      evt = wh.verify(body, {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
      }) as WebhookEvent;
    } catch (err) {
      console.error("Error verifying webhook:", err);
      return new Response("Error occurred", { status: 400 });
    }

    const eventType = evt.type;

    if (eventType === "user.created") {
      const { id, first_name, last_name, image_url, email_addresses } =
        evt.data;
      const email = email_addresses[0].email_address;
      const name = `${first_name || ""} ${last_name || ""}`.trim();

      try {
        await ctx.runMutation(api.users.syncUser, {
          email,
          name,
          image: image_url,
          clerkId: id,
        });
      } catch (error) {
        console.log("Error creating user:", error);
        return new Response("Error creating user", { status: 500 });
      }
    }

    if (eventType === "user.updated") {
      const { id, email_addresses, first_name, last_name, image_url } =
        evt.data;
      const email = email_addresses[0].email_address;
      const name = `${first_name || ""} ${last_name || ""}`.trim();

      try {
        await ctx.runMutation(api.users.updateUser, {
          clerkId: id,
          email,
          name,
          image: image_url,
        });
      } catch (error) {
        console.log("Error updating user:", error);
        return new Response("Error updating user", { status: 500 });
      }
    }

    return new Response("Webhooks processed successfully", { status: 200 });
  }),
});

// Fitness plan generation route
http.route({
  path: "/vapi/generate-program",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    try {
      const payload = await request.json();
      const pythonApiUrl = "http://localhost:8000/api/fitness_generator";
      console.log("[CONVEX] Sending request to Python backend:", {
        url: pythonApiUrl,
        payload,
        headers: { "Content-Type": "application/json" },
      });

      const response = await fetch(pythonApiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      console.log("[CONVEX] Python backend response status:", response.status);
      const responseText = await response.text();
      console.log("[CONVEX] Python backend raw response:", responseText);

      if (!response.ok) {
        throw new Error(
          `Python API error: ${response.status} - ${responseText}`
        );
      }

      let result;
      try {
        result = JSON.parse(responseText);
      } catch (parseErr) {
        throw new Error(
          `Failed to parse Python backend JSON: ${parseErr} | Raw: ${responseText}`
        );
      }
      console.log("Python backend response (parsed):", result);

      if (result.success && result.data && result.data.success) {
        const planToSave = {
          userId: payload.user_id,
          dietPlan: result.data.diet_plan,
          isActive: true,
          workoutPlan: result.data.workout_plan,
          name: payload.name || "Fitness Plan",
        };
        console.log("[CONVEX] Plan object to save:", planToSave);
        const planId = await ctx.runMutation(api.plans.createPlan, planToSave);
        console.log("[CONVEX] Saved planId:", planId);

        return new Response(
          JSON.stringify({
            ...result,
            planId,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      } else {
        return new Response(JSON.stringify(result), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
    } catch (error) {
      console.error("[CONVEX] Error generating fitness plan:", error);
      return new Response(
        JSON.stringify({
          success: false,
          error: error instanceof Error ? error.message : String(error),
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
  }),
});

export default http;
