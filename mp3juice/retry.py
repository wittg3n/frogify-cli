from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    name: str
    theta_429_backoff_s: tuple[float, ...]
    theta_429_max_retries: int
    theta_retry_after_cap_s: float
    theta_transient_delays_s: tuple[float, ...]
    theta_min_request_interval_s: float
    theta_recovery_request_interval_s: float
    theta_recovery_success_requests: int
    convert_poll_attempts: int
    convert_poll_delays_s: tuple[float, ...]
    direct_audio_retry_delays_s: tuple[float, ...]


RETRY_PROFILES: dict[str, RetryPolicy] = {
    # Default: enough pacing to reduce 429s, but bounded waits so an 800-track
    # library does not stall on one candidate.
    "balanced": RetryPolicy(
        name="balanced",
        theta_429_backoff_s=(2.0, 5.0),
        theta_429_max_retries=2,
        theta_retry_after_cap_s=5.0,
        theta_transient_delays_s=(1.0, 2.0),
        theta_min_request_interval_s=0.20,
        theta_recovery_request_interval_s=0.50,
        theta_recovery_success_requests=10,
        convert_poll_attempts=3,
        convert_poll_delays_s=(0.35, 0.75),
        direct_audio_retry_delays_s=(0.50,),
    ),
    "fast": RetryPolicy(
        name="fast",
        theta_429_backoff_s=(1.5,),
        theta_429_max_retries=1,
        theta_retry_after_cap_s=2.0,
        theta_transient_delays_s=(0.75,),
        theta_min_request_interval_s=0.08,
        theta_recovery_request_interval_s=0.25,
        theta_recovery_success_requests=4,
        convert_poll_attempts=2,
        convert_poll_delays_s=(0.35,),
        direct_audio_retry_delays_s=(0.35,),
    ),
    "patient": RetryPolicy(
        name="patient",
        theta_429_backoff_s=(3.0, 7.0, 12.0),
        theta_429_max_retries=3,
        theta_retry_after_cap_s=15.0,
        theta_transient_delays_s=(1.5, 3.0, 6.0),
        theta_min_request_interval_s=0.35,
        theta_recovery_request_interval_s=0.75,
        theta_recovery_success_requests=18,
        convert_poll_attempts=4,
        convert_poll_delays_s=(0.50, 1.00, 1.50),
        direct_audio_retry_delays_s=(0.75, 1.50),
    ),
}


def get_retry_policy(name: str) -> RetryPolicy:
    key = (name or "balanced").strip().lower()
    try:
        return RETRY_PROFILES[key]
    except KeyError as exc:
        choices = ", ".join(RETRY_PROFILES)
        raise ValueError(f"retry_profile must be one of: {choices}") from exc
