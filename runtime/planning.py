"""Small conservative 0/1 knapsack on predicted costs, with bounded DP memory."""
import math


def knapsack(items,budget,max_states=4096):
    """items=(expected reward, expected cost); returns selected original indices.

    Costs round upward, budget downward. The optimum is exact for this discretization,
    not for the unknown stochastic costs of actual attempts.
    """
    if not math.isfinite(budget) or budget<=0:return []
    quantum=max(1,math.ceil(budget/max_states));capacity=int(budget//quantum)
    dp=[float('-inf')]*(capacity+1);dp[0]=0
    masks=[0]*(capacity+1)
    for i,(value,cost) in enumerate(items):
        if value<=0 or cost<=0 or not math.isfinite(value+cost):continue
        weight=math.ceil(cost/quantum)
        if weight>capacity:continue
        for available in range(capacity,weight-1,-1):
            candidate=dp[available-weight]+value
            if candidate>dp[available]:
                dp[available]=candidate;masks[available]=masks[available-weight]|(1<<i)
    mask=masks[max(range(capacity+1),key=dp.__getitem__)]
    return [i for i in range(len(items)) if mask&(1<<i)]
