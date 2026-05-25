import numpy as np
import random
import os
from backtester.engine import BacktestEngine

class GeneticOptimizer:
    def __init__(self, strategy_class, data_dict, population_size=20, generations=10):
        self.strategy_class = strategy_class
        self.data_dict = data_dict
        self.pop_size = population_size
        self.generations = generations
        self.engine = BacktestEngine()

    def generate_initial_population(self):
        """초기 유전자 세대 생성 (K값: 0.3~0.7, RSI: 20~40)"""
        population = []
        for _ in range(self.pop_size):
            genome = {
                'k_value': random.uniform(0.3, 0.7),
                'rsi_threshold': random.randint(20, 40)
            }
            population.append(genome)
        return population

    def fitness(self, genome):
        """유전자 성능 평가 (백테스트 수익률)"""
        # 임시 전략 인스턴스 생성 및 테스트
        # (실제 구현 시에는 전략 객체에 게놈 주입)
        return random.uniform(-10, 50) # 예시 수익률

    def evolve(self):
        """진화 프로세스 실행"""
        population = self.generate_initial_population()
        
        for gen in range(self.generations):
            # 1. 평가 및 정렬
            population = sorted(population, key=lambda g: self.fitness(g), reverse=True)
            print(f"Generation {gen}: Best Fitness = {self.fitness(population[0]):.2f}")
            
            # 2. 다음 세대 구성 (상위 20%는 보존)
            next_gen = population[:int(self.pop_size * 0.2)]
            
            # 3. 교차 및 돌연변이
            while len(next_gen) < self.pop_size:
                parent1, parent2 = random.sample(population[:10], 2)
                child = {
                    'k_value': (parent1['k_value'] + parent2['k_value']) / 2 * random.uniform(0.9, 1.1),
                    'rsi_threshold': random.choice([parent1['rsi_threshold'], parent2['rsi_threshold']])
                }
                next_gen.append(child)
            population = next_gen

        best_genome = population[0]
        self.update_config(best_genome)
        return best_genome

    def update_config(self, best_genome):
        """최적의 파라미터로 .env 자동 업데이트"""
        try:
            env_file = '.env'
            if not os.path.exists(env_file):
                env_file = '.env.sample'
            
            if os.path.exists(env_file):
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('K_VALUE='):
                        lines[i] = f"K_VALUE={best_genome['k_value']:.4f}\n"
                        updated = True
                        break
                
                if not updated:
                    lines.append(f"\nK_VALUE={best_genome['k_value']:.4f}\n")
                
                # Write to .env (not .env.sample to protect the sample file)
                with open('.env', 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print("✅ 최적화된 파라미터가 .env에 반영되었습니다.")
            else:
                print("❌ .env 또는 .env.sample 파일을 찾을 수 없어 파라미터를 업데이트하지 못했습니다.")
        except Exception as e:
            print(f"설정 파일 업데이트 실패: {str(e)}")
