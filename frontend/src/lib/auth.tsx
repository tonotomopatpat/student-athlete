import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ApiError, request, type User } from "./api";
import { LoadingBlock } from "../components/ui";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await request<User>("/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return async () => {
    await request("/auth/logout", { method: "POST" });
    client.clear();
    client.setQueryData(["me"], null);
  };
}

export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="mx-auto max-w-md p-6">
        <LoadingBlock label="Checking your session" />
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-md p-6" role="alert">
        <h1 className="text-3xl">Server unavailable</h1>
        <p className="mt-2 text-ink-soft">We could not reach Sideline. Check your connection and reload the page.</p>
      </div>
    );
  }
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}
