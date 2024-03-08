"""
Module managing an ant colony in a labyrinth.
"""
import numpy as np
import maze
import pheromone
import direction as d
import pygame as pg
from mpi4py import MPI


#on fait aussi un import de la librairie math
#on utilisera la fonctionn floor pour partager les index parmi les cores de calcul
from math import floor

#on cree les communicateurs
comm =MPI.COMM_WORLD
rank_i = comm.Get_rank()
size_i = comm.Get_size()

new_comm = comm.Create_group(comm.group.Excl([0]))
if rank_i != 0:
    rank_f = new_comm.Get_rank()
    size_f = new_comm.Get_size()
    


comm_display = comm.Create_group(comm.group.Incl([0,1]))
UNLOADED, LOADED = False, True

exploration_coefs = 0.


class Colony:
    """
    Represent an ant colony. Ants are not individualized for performance reasons!

    Inputs :
        nb_ants  : Number of ants in the anthill
        pos_init : Initial positions of ants (anthill position)
        max_life : Maximum life that ants can reach
    """
    def __init__(self, nb_ants, pos_init, max_life,index_min,index_max):
        #parametros que eu botei
        self.index_min = index_min
        self.index_max = index_max
        # Each ant has is own unique random seed
        self.seeds = np.arange(index_min+1, index_max+1, dtype=np.int64)
        # State of each ant : loaded or unloaded
        self.is_loaded = np.zeros(nb_ants, dtype=np.int8)
        # Compute the maximal life amount for each ant :
        #   Updating the random seed :
        self.seeds[:] = np.mod(16807*self.seeds[:], 2147483647)
        # Amount of life for each ant = 75% à 100% of maximal ants life
        self.max_life = max_life * np.ones(nb_ants, dtype=np.int32)
        self.max_life -= np.int32(max_life*(self.seeds/2147483647.))//4
        # Ages of ants : zero at beginning
        self.age = np.zeros(nb_ants, dtype=np.int64)
        # History of the path taken by each ant. The position at the ant's age represents its current position.
        self.historic_path = np.zeros((nb_ants, max_life+1, 2), dtype=np.int16)
        self.historic_path[:, 0, 0] = pos_init[0]
        self.historic_path[:, 0, 1] = pos_init[1]
        # Direction in which the ant is currently facing (depends on the direction it came from).
        self.directions = d.DIR_NONE*np.ones(nb_ants, dtype=np.int8)
        self.sprites = []
        img = pg.image.load("ants.png").convert_alpha()
        for i in range(0, 32, 8):
            self.sprites.append(pg.Surface.subsurface(img, i, 0, 8, 8))

    def return_to_nest(self, loaded_ants, pos_nest, food_counter):
        """
        Function that returns the ants carrying food to their nests.

        Inputs :
            loaded_ants: Indices of ants carrying food
            pos_nest: Position of the nest where ants should go
            food_counter: Current quantity of food in the nest

        Returns the new quantity of food
        """
        self.age[loaded_ants] -= 1
        #a gente pode separar os indices do loaded antes

        in_nest_tmp = self.historic_path[loaded_ants, self.age[loaded_ants], :] == pos_nest
        if in_nest_tmp.any():
            in_nest_loc = np.nonzero(np.logical_and(in_nest_tmp[:, 0], in_nest_tmp[:, 1]))[0]
            if in_nest_loc.shape[0] > 0:
                in_nest = loaded_ants[in_nest_loc]
                self.is_loaded[in_nest] = UNLOADED
                self.age[in_nest] = 0
                food_counter += in_nest_loc.shape[0]
        return food_counter

    def explore(self, unloaded_ants, the_maze, pos_food, pos_nest, pheromones):
        """
        Management of unloaded ants exploring the maze.

        Inputs:
            unloadedAnts: Indices of ants that are not loaded
            maze        : The maze in which ants move
            posFood     : Position of food in the maze
            posNest     : Position of the ants' nest in the maze
            pheromones  : The pheromone map (which also has ghost cells for
                          easier edge management)

        Outputs: None
        """
        index_min = floor(rank_f * self.age.shape[0]/size_f)
        index_max = floor((rank_f+1) * self.age.shape[0]/size_f)
        # Update of the random seed (for manual pseudo-random) applied to all unloaded ants
        #mudanca aqui
        
        self.seeds[unloaded_ants] = np.mod(16807*self.seeds[unloaded_ants], 2147483647)
        choices = self.seeds[:] / 2147483647.

        # Calculating possible exits for each ant in the maze:
        #old_pos_ants = self.historic_path[range(0, self.seeds.shape[0]), self.age[:], :]
        old_pos_ants = self.historic_path[range(0, self.seeds.shape[0]), self.age[:], :]
        has_north_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.NORTH) > 0
        has_east_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.EAST) > 0
        has_south_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.SOUTH) > 0
        has_west_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.WEST) > 0

        # Reading neighboring pheromones:
        north_pos = np.copy(old_pos_ants)
        north_pos[:, 1] += 1
        north_pheromone = pheromones.pheromon[north_pos[:, 0], north_pos[:, 1]]*has_north_exit

        east_pos = np.copy(old_pos_ants)
        east_pos[:, 0] += 1
        east_pos[:, 1] += 2
        east_pheromone = pheromones.pheromon[east_pos[:, 0], east_pos[:, 1]]*has_east_exit

        south_pos = np.copy(old_pos_ants)
        south_pos[:, 0] += 2
        south_pos[:, 1] += 1
        south_pheromone = pheromones.pheromon[south_pos[:, 0], south_pos[:, 1]]*has_south_exit

        west_pos = np.copy(old_pos_ants)
        west_pos[:, 0] += 1
        west_pheromone = pheromones.pheromon[west_pos[:, 0], west_pos[:, 1]]*has_west_exit

        max_pheromones = np.maximum(north_pheromone, east_pheromone)
        max_pheromones = np.maximum(max_pheromones, south_pheromone)
        max_pheromones = np.maximum(max_pheromones, west_pheromone)
        #on partage les taches
        # Calculating choices for all ants not carrying food (for others, we calculate but it doesn't matter)
        

        # Ants explore the maze by choice or if no pheromone can guide them:
        ind_exploring_ants = np.nonzero(
            np.logical_or(choices[unloaded_ants] <= exploration_coefs, max_pheromones[unloaded_ants] == 0.))[0]
        if ind_exploring_ants.shape[0] > 0:
            ind_exploring_ants = unloaded_ants[ind_exploring_ants]
            valid_moves = np.zeros(choices.shape[0], np.int8)
            nb_exits = has_north_exit * np.ones(has_north_exit.shape) + has_east_exit * np.ones(has_east_exit.shape) + \
                has_south_exit * np.ones(has_south_exit.shape) + has_west_exit * np.ones(has_west_exit.shape)
            while np.any(valid_moves[ind_exploring_ants] == 0):
                # Calculating indices of ants whose last move was not valid:
                ind_ants_to_move = ind_exploring_ants[valid_moves[ind_exploring_ants] == 0]
                self.seeds[:] = np.mod(16807*self.seeds[:], 2147483647)
                # Choosing a random direction:
                #atualisar os new_pos entre todos os processos de calculo
                dir = np.mod(self.seeds[ind_ants_to_move], 4)
                old_pos = self.historic_path[ind_ants_to_move, self.age[ind_ants_to_move], :]
                new_pos = np.copy(old_pos)
                new_pos[:, 1] -= np.logical_and(dir == d.DIR_WEST,
                                                has_west_exit[ind_ants_to_move]) * np.ones(new_pos.shape[0], dtype=np.int16)
                new_pos[:, 1] += np.logical_and(dir == d.DIR_EAST,
                                                has_east_exit[ind_ants_to_move]) * np.ones(new_pos.shape[0], dtype=np.int16)
                new_pos[:, 0] -= np.logical_and(dir == d.DIR_NORTH,
                                                has_north_exit[ind_ants_to_move]) * np.ones(new_pos.shape[0], dtype=np.int16)
                new_pos[:, 0] += np.logical_and(dir == d.DIR_SOUTH,
                                                has_south_exit[ind_ants_to_move]) * np.ones(new_pos.shape[0], dtype=np.int16)
                # Valid move if we didn't stay in place due to a wall
                valid_moves[ind_ants_to_move] = np.logical_or(new_pos[:, 0] != old_pos[:, 0], new_pos[:, 1] != old_pos[:, 1])
                # and if we're not in the opposite direction of the previous move (and if there are other exits)
                valid_moves[ind_ants_to_move] = np.logical_and(
                    valid_moves[ind_ants_to_move],
                    np.logical_or(dir != 3-self.directions[ind_ants_to_move], nb_exits[ind_ants_to_move] == 1))
                # Calculating indices of ants whose move we just validated:
                ind_valid_moves = ind_ants_to_move[np.nonzero(valid_moves[ind_ants_to_move])[0]]
                # For these ants, we update their positions and directions
                #mudanca
                #ind_valid_moves, new_pos, ind_ants_to_move
                self.historic_path[ind_valid_moves, self.age[ind_valid_moves] + 1, :] = new_pos[valid_moves[ind_ants_to_move] == 1, :]
                self.directions[ind_valid_moves] = dir[valid_moves[ind_ants_to_move] == 1]
                #self.historic_path = np.vstack(new_comm.allgather(self.historic_path[index_min:index_max]))
                #self.directions = np.hstack(new_comm.allgather(self.directions[index_min:index_max]))
            #nesse ponto cada processador de calculo tem uma versao do historico
            #q passou por varias mudancas... as direcoes tambem
            #ou mudamos localmente e depois juntamos todas as mudancas
            #juntar depois, usando o unloaded ants, ja que so essas foram mexidas
            #
            #print("shape history", np.shape(self.historic_path))
        ind_following_ants = np.nonzero(np.logical_and(choices[unloaded_ants] > exploration_coefs,
                                                       max_pheromones[unloaded_ants] > 0.))[0]
        if ind_following_ants.shape[0] > 0:
            ind_following_ants = unloaded_ants[ind_following_ants]
            self.historic_path[ind_following_ants, self.age[ind_following_ants] + 1, :] = \
                self.historic_path[ind_following_ants, self.age[ind_following_ants], :]
            max_east = (east_pheromone[ind_following_ants] == max_pheromones[ind_following_ants])
            self.historic_path[ind_following_ants, self.age[ind_following_ants]+1, 1] += \
                max_east * np.ones(ind_following_ants.shape[0], dtype=np.int16)
            max_west = (west_pheromone[ind_following_ants] == max_pheromones[ind_following_ants])
            self.historic_path[ind_following_ants, self.age[ind_following_ants]+1, 1] -= \
                max_west * np.ones(ind_following_ants.shape[0], dtype=np.int16)
            max_north = (north_pheromone[ind_following_ants] == max_pheromones[ind_following_ants])
            self.historic_path[ind_following_ants, self.age[ind_following_ants]+1, 0] -= max_north * np.ones(ind_following_ants.shape[0], dtype=np.int16)
            max_south = (south_pheromone[ind_following_ants] == max_pheromones[ind_following_ants])
            self.historic_path[ind_following_ants, self.age[ind_following_ants]+1, 0] += max_south * np.ones(ind_following_ants.shape[0], dtype=np.int16)
            #self.historic_path = np.vstack(new_comm.allgather(self.historic_path[index_min:index_max]))
            
        # Aging one unit for the age of ants not carrying food
        if unloaded_ants.shape[0] > 0:
            self.age[unloaded_ants] += 1

        # Killing ants at the end of their life:
        ind_dying_ants = np.nonzero(self.age == self.max_life)[0]
        if ind_dying_ants.shape[0] > 0:
            self.age[ind_dying_ants] = 0
            self.historic_path[ind_dying_ants, 0, 0] = pos_nest[0]
            self.historic_path[ind_dying_ants, 0, 1] = pos_nest[1]
            self.directions[ind_dying_ants] = d.DIR_NONE

        # For ants reaching food, we update their states:
        ants_at_food_loc = np.nonzero(np.logical_and(self.historic_path[unloaded_ants, self.age[unloaded_ants], 0] == pos_food[0],
                                                     self.historic_path[unloaded_ants, self.age[unloaded_ants], 1] == pos_food[1]))[0]
        if ants_at_food_loc.shape[0] > 0:
            ants_at_food = unloaded_ants[ants_at_food_loc]
            #mudanca
            self.is_loaded[ants_at_food] = True
        #apres explore, chaque processus de calcule a une partie des attributes
        #de la collone. on doit appeler un allgather, ainsi tous les processus
        #auront les arrays mis a jour
        
    def advance(self, the_maze, pos_food, pos_nest, pheromones,food_counter=0):
        
        if not new_comm == MPI.COMM_NULL:
            
            loaded_ants = np.nonzero(self.is_loaded == True)[0]
            unloaded_ants = np.nonzero(self.is_loaded == False)[0]
            if food_counter is None:
                    food_counter = 0
            if loaded_ants.shape[0] > 0:
                #on trouve les index pour chaque processeur de calcul
                #acho q posso jogar esse loaded _ants ja com os indices certos
                food_counter = self.return_to_nest(loaded_ants, pos_nest, food_counter)
            new_comm.barrier()
        food_counter = comm.reduce(food_counter,op = MPI.SUM,root=0)
        if not new_comm == MPI.COMM_NULL:
            # self.age = np.hstack(new_comm.allgather(self.age[index_min:index_max]))
            # self.is_loaded = np.hstack(new_comm.allgather(self.is_loaded[index_min:index_max]))
            #aqui atualizamos o age e a posicao, ja que as formigas com comida foram manda
            #das pra casa
            #precisamos atualizar isloaded, age e o foodcounter tem q ser reduzido
            # self.age = np.hstack(new_comm.allgather(self.age[index_min:index_max]))
            # self.is_loaded = np.hstack(new_comm.allgather(self.is_loaded[index_min:index_max]))
            if unloaded_ants.shape[0] > 0:
                #acho q o explore nao chama nenhuma coisa mto complicada, pode ser totalmente
                #paralelizado, a matriz pheromones dentro dele nao passa nenhuma modificacao
                self.explore(unloaded_ants, the_maze, pos_food, pos_nest, pheromones)
            new_comm.barrier()
            # self.seeds = np.hstack(new_comm.allgather(self.seeds[index_min:index_max]))
            # self.age = np.hstack(new_comm.allgather(self.age[index_min:index_max]))
            # self.is_loaded = np.hstack(new_comm.allgather(self.is_loaded[index_min:index_max]))
            # self.historic_path = np.vstack(new_comm.allgather(self.historic_path[index_min:index_max]))
            # self.directions = np.hstack(new_comm.allgather(self.directions[index_min:index_max]))
            #on partage les phereomones
            
            old_pos_ants = self.historic_path[range(0, self.seeds.shape[0]), self.age[:], :]
            has_north_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.NORTH) > 0
            has_east_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.EAST) > 0
            has_south_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.SOUTH) > 0
            has_west_exit = np.bitwise_and(the_maze.maze[old_pos_ants[:, 0], old_pos_ants[:, 1]], maze.WEST) > 0

                # Marking pheromones:
            
            old_pheromones = pheromones.pheromon.copy()
            #old_pheromones = result
            [pheromones.mark(self.historic_path[i, self.age[i], :],
                        [has_north_exit[i], has_east_exit[i], 
                        has_west_exit[i], has_south_exit[i]],
                        old_pheromones) for i in range(self.directions.shape[0])]
            
            result= np.zeros_like(pheromones.pheromon)
            new_comm.Allreduce(pheromones.pheromon,result, op = MPI.MAX)
            pheromones.pheromon = result.copy()
        #pheromones.pheromon = comm_display.bcast(pheromones.pheromon,root = 1)
        #maintenant on fait une communication pour mettre a jour tous
        #les instances de collones dans chaque processeur
        #rank_i = 1 dans le communicateur general est le responsable pour les fourmis
        # if rank_i==0:
        #     food_counter=0
        #food_counter = comm.reduce(food_counter,op = MPI.SUM,root = 0)
        # if rank_i==0:
        #     print("check for 0",food_counter)
        if not comm_display == MPI.COMM_NULL:
            #food_counter = comm_display.bcast(food_counter,root = 1)
            self.seeds = np.hstack(comm_display.bcast(np.array(self.seeds),root = 1))
            self.is_loaded = comm_display.bcast(np.array(self.is_loaded),root =1)
            self.max_life = comm_display.bcast(np.array(self.max_life),root =1)
            self.age = comm_display.bcast(np.array(self.age),root =1)
            self.historic_path = comm_display.bcast(np.array(self.historic_path),root =1)
            self.directions = comm_display.bcast(np.array(self.directions),root =1)
            pheromones.pheromon=comm_display.bcast(pheromones.pheromon,root=1)
        return food_counter

    def display(self, screen):
        [screen.blit(self.sprites[self.directions[i]], (8*self.historic_path[i, self.age[i], 1], 8*self.historic_path[i, self.age[i], 0])) for i in range(self.directions.shape[0])]


if __name__ == "__main__":
    import sys
    import time
    
    pg.init()
    size_laby = 25, 25
    if len(sys.argv) > 2:
        size_laby = int(sys.argv[1]),int(sys.argv[2])

    resolution = size_laby[1]*8, size_laby[0]*8
    if rank_i == 0:
        screen = pg.display.set_mode(resolution)
    if rank_i != 0:#les autres processeurs ne vont pas creer une ecran
        screen = pg.display.set_mode((0,0),pg.HIDDEN|pg.NOFRAME | pg.HWSURFACE | pg.DOUBLEBUF)
        
    #la definition du nombre de fourmis    
    nb_ants = size_laby[0]*size_laby[1]//4
    max_life = 500
    if len(sys.argv) > 3:
        max_life = int(sys.argv[3])

    #definition de la position de la nourriture
    pos_food = size_laby[0]-1, size_laby[1]-1
    pos_nest = 0, 0
    #creation du labyrinthe
    
    a_maze = maze.Maze(size_laby, 12345)
    #les formis qui seront creees
    if rank_i==0:
        ants = Colony(nb_ants, pos_nest, max_life,0,nb_ants)
    if rank_i!=0:
        index_min = floor(rank_f * nb_ants/size_f)
        index_max = floor((rank_f+1) * nb_ants/size_f)
        ants = Colony(index_max-index_min, pos_nest, max_life,index_min,index_max)
    unloaded_ants = np.array(range(nb_ants))
    alpha = 0.9
    beta  = 0.99
    if len(sys.argv) > 4:
        alpha = float(sys.argv[4])
    if len(sys.argv) > 5:
        beta = float(sys.argv[5])
    #creation de la matrice de pheromones
    pherom = pheromone.Pheromon(size_laby, pos_food, alpha, beta)
    if rank_i == 0:
        mazeImg = a_maze.display()
    food_counter = 0
    
    finish = False

    snapshop_taken = False
    deb_1 = time.time()
    while True:
          
        #ici l'ecran de 0 sera la seule visualisée
        if rank_i == 0:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    pg.quit()
                    finish = True
                    #continue#on chagne le status du boucle et on 
        finish = comm.bcast(finish,root=0)
        if finish:
            exit(0)            
        

        
        #affichage de la grille, de la collone et des pheromones
        if rank_i==0:
            pherom.display(screen)
            screen.blit(mazeImg, (0, 0))
            ants.display(screen)
            pg.display.update()
        #avanco das formigas?
        deb = time.time()
        food_counter = ants.advance(a_maze, pos_food, pos_nest, pherom, food_counter)
        #evaporacao do feromonio com bheta
        pherom.do_evaporation(pos_food)
        end = time.time()
        if rank_i==0:
            if food_counter == 1 and not snapshop_taken:
                pg.image.save(screen, "MyFirstFood.png")
                snapshop_taken = True
            #pg.time.wait(500)
            if food_counter >= 1000:
                print("Time to reach 1000 foods: ",end - deb_1)
                pg.quit()
                finish=True
                continue
            print(f"FPS : {1./(end-deb):6.2f}, nourriture : {food_counter:7d}" ,end='\r')
            