export type Page = "leaderboard" | "my-profile" | "profiles" | "settings" | "admin";

export interface TierDefinition {
  name: string;
  points: number;
  color: string;
}

export interface Catalog {
  kits: string[];
  tiers: TierDefinition[];
  roles: Array<{ name: string; color: string }>;
  titles: Array<{ name: string; color: string }>;
}

export interface KitStats {
  kit: string;
  tier: string;
  points: number;
  wins: number;
  losses: number;
  matches: number;
  winrate: number;
}

export interface Player {
  uuid: string;
  username: string;
  verified: boolean;
  role_name: string | null;
  title_name: string | null;
  overall_tier: string;
  overall_average_points: number;
  kits: KitStats[];
}

export interface LeaderboardEntry {
  uuid: string;
  username: string;
  role_name: string | null;
  title_name: string | null;
  tier: string;
  points?: number;
  average_points?: number;
  wins?: number;
  losses?: number;
  matches?: number;
  winrate?: number;
  rank: number;
}

export interface PageResult<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface MatchRecord {
  id: number;
  idempotency_key: string;
  kit: string;
  winner_uuid: string;
  loser_uuid: string;
  winner_tier_before: string;
  loser_tier_before: string;
  winner_tier_after: string;
  loser_tier_after: string;
  created_at: string;
}

export interface AdminLog {
  id: number;
  admin_username: string;
  action: string;
  target_uuid: string | null;
  details: Record<string, unknown>;
  created_at: string;
}
