#![no_std]

use soroban_sdk::{contract, contractimpl, symbol_short, Env};

#[contract]
pub struct Counter;

#[contractimpl]
impl Counter {
    pub fn increment(env: Env) -> u32 {
        let key = symbol_short!("count");
        let next = env.storage().instance().get::<_, u32>(&key).unwrap_or(0) + 1;
        env.storage().instance().set(&key, &next);
        next
    }
}
